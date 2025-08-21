from typing import Annotated
import fastapi
from starlette.requests import Request
from starlette.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi import Form, File, UploadFile, Query
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from plotly.utils import PlotlyJSONEncoder
from plotly.express.colors import sample_colorscale
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import glob
import re

from models.aquacrop_model import aquacrop_run_ussana, aquacrop_run_benatzu, run_ensemble_and_generate_plot

import openmeteo_requests
from openmeteo_sdk.Variable import Variable
import requests_cache
from retry_requests import retry

import folium
import geopandas as gpd
import rasterio
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from rasterstats import zonal_stats
from rasterio.mask import mask
from shapely.geometry import mapping
from pathlib import Path

from rasterio.transform import from_bounds
from sentinelhub import (
    SHConfig, BBox, CRS, DataCollection, SentinelHubCatalog,
    SentinelHubRequest, MimeType, bbox_to_dimensions, filter_times
)


templates = Jinja2Templates('templates')
router = fastapi.APIRouter()

@router.get('/', include_in_schema=False)
async def index(request: Request):
    return templates.TemplateResponse('index.html', {'request': request})

@router.get('/simulation', include_in_schema=False)
async def index(request: Request):
    return templates.TemplateResponse('simulation.html', {'request': request})

@router.get('/documentation', include_in_schema=False)
async def index(request: Request):
    return templates.TemplateResponse('documentation.html', {'request': request})

@router.get('/favicon.ico', include_in_schema=False)
def favicon():
    return fastapi.responses.RedirectResponse(url='https://arsinoe-project.eu/securstorage/2022/02/favicon-32.png')


@router.get(
    "/gfs_forecast/{latitude}/{longitude}",
    summary="GFS ensemble boxplots for precipitation, ET0, wind speed and temperature",
    description=(
        "Fetches weather forecasts from the **Open-Meteo Ensemble API** (`gfs_seamless` model) "
        "for the provided coordinates and builds **daily statistics** by aggregating ensemble members.\n\n"
        "**Workflow:**\n"
        "1. Calls the endpoint `https://ensemble-api.open-meteo.com/v1/ensemble` with *latitude*, *longitude*, "
        "hourly variables `temperature_2m`, `precipitation`, `et0_fao_evapotranspiration`, `wind_speed_10m`, `surface_temperature`, "
        "`forecast_days=36` and `temporal_resolution=native` on the model `gfs_seamless`.\n"
        "2. Converts the response into an **hourly dataframe** containing all ensemble members "
        "(M00 = control run, M01..M30 = stochastic members).\n"
        "3. Computes a **daily dataframe** with:\n"
        "   - 2m temperature: mean/min/max per member\n"
        "   - Precipitation: 24h sum per member\n"
        "   - ET0 FAO: 24h sum per member\n"
        "   - 10m wind speed: daily max per member\n"
        "4. Generates a Plotly figure with **4 subplots** sharing the x-axis, showing for the first 16 days "
        "a **boxplot of all ensemble members (M01..M30)** and the **control member (M00)** as a line:\n"
        "   - Panel 1: *Total precipitation [mm/24h]*\n"
        "   - Panel 2: *Total ET0 FAO evapotranspiration [mm/24h]*\n"
        "   - Panel 3: *10m wind speed max [m/s]*\n"
        "   - Panel 4: *2m temperature min/max [°C]* (control run lines for min/max)\n\n"
        "The endpoint returns the **Plotly figure as JSON**, ready to be rendered on the client side "
        "(e.g. with `Plotly.newPlot(...)`)."
    ),
    tags=["Forecast", "GFS", "Open-Meteo"],
    response_description="Plotly figure serialized as JSON, including boxplots of ensemble members and the control run line.",
    responses={
        200: {
            "description": "Figure successfully generated (Plotly JSON).",
            "content": {
                "application/json": {
                    "example": {
                        "data": [{"type": "box", "y": [1, 2, 3]}],
                        "layout": {"title": "GFS forecast"}
                    }
                }
            }
        },
        422: {"description": "Invalid parameters (lat/long out of range, wrong types)."},
        503: {"description": "Upstream weather service unavailable or temporary timeout."}
    },
    include_in_schema=True,
)
async def gfs_forecast(
    latitude: float = fastapi.Path(..., ge=-90, le=90, description="Latitude in decimal degrees (−90 … +90)."),
    longitude: float = fastapi.Path(..., ge=-180, le=180, description="Longitude in decimal degrees (−180 … +180).")
) -> dict:
    """
    Returns the Plotly figure as JSON. See the detailed description above.
    """
    # Setup the Open-Meteo API client with cache and retry on error
    cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    # Make sure all required weather variables are listed here
    # The order of variables in hourly or daily is important to assign them correctly below
    url = "https://ensemble-api.open-meteo.com/v1/ensemble"
    params = {
        "latitude": latitude, #39.415
        "longitude": longitude, #9.1
        "hourly": ["temperature_2m", "precipitation", "et0_fao_evapotranspiration", "wind_speed_10m", "surface_temperature"],
        "forecast_days": 36,
        "temporal_resolution": "native",
        "models": "gfs_seamless"
    }
    responses = openmeteo.weather_api(url, params=params)

    # Process first location. Add a for-loop for multiple locations or weather models
    response = responses[0]
    print(f"Coordinates {response.Latitude()}°N {response.Longitude()}°E")
    print(f"Elevation {response.Elevation()} m asl")
    print(f"Timezone {response.Timezone()} {response.TimezoneAbbreviation()}")
    print(f"Timezone difference to GMT+0 {response.UtcOffsetSeconds()} s")

    # Process hourly data
    hourly = response.Hourly()
    hourly_variables = list(map(lambda i: hourly.Variables(i), range(0, hourly.VariablesLength())))

    hourly_temperature_2m = filter(lambda x: x.Variable() == Variable.temperature and x.Altitude() == 2, hourly_variables)

    hourly_precipitation = filter(lambda x: x.Variable() == Variable.precipitation, hourly_variables)

    hourly_et0_fao_evapotranspiration = filter(lambda x: x.Variable() == Variable.et0_fao_evapotranspiration, hourly_variables)

    hourly_wind_speed_10m = filter(lambda x: x.Variable() == Variable.wind_speed and x.Altitude() == 10, hourly_variables)

    hourly_data = {"date": pd.date_range(
        start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
        end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True) - pd.Timedelta(seconds=hourly.Interval()),
        freq=pd.Timedelta(seconds=hourly.Interval())
    )}

    # Process all members

    for variable in hourly_temperature_2m:
        member = variable.EnsembleMember()
        hourly_data[f"temperature_2m_M{member:02d}"] = variable.ValuesAsNumpy()

    for variable in hourly_precipitation:
        member = variable.EnsembleMember()
        hourly_data[f"precipitation_M{member:02d}"] = variable.ValuesAsNumpy()

    for variable in hourly_et0_fao_evapotranspiration:
        member = variable.EnsembleMember()
        hourly_data[f"et0_fao_evapotranspiration_M{member:02d}"] = variable.ValuesAsNumpy()

    for variable in hourly_wind_speed_10m:
        member = variable.EnsembleMember()
        hourly_data[f"wind_speed_10m_M{member:02d}"] = variable.ValuesAsNumpy()

    hourly_dataframe = pd.DataFrame(data = hourly_data)

    hourly_dataframe.index = hourly_dataframe.date
    hourly_dataframe = hourly_dataframe.drop(['date'], axis=1)

    # Daily dataframe
    daily_dataframe = hourly_dataframe[[f'temperature_2m_M{m:02d}' for m in range(31)]].resample('D').mean().add_prefix('mean_')
    daily_dataframe = pd.concat([daily_dataframe, hourly_dataframe[[f'temperature_2m_M{m:02d}' for m in range(31)]].resample('D').min().add_prefix('min_')], axis=1)
    daily_dataframe = pd.concat([daily_dataframe, hourly_dataframe[[f'temperature_2m_M{m:02d}' for m in range(31)]].resample('D').max().add_prefix('max_')], axis=1)
    daily_dataframe = pd.concat([daily_dataframe, hourly_dataframe[[f'precipitation_M{m:02d}' for m in range(31)]].resample('D').sum().add_prefix('sum_')], axis=1)
    daily_dataframe = pd.concat([daily_dataframe, hourly_dataframe[[f'et0_fao_evapotranspiration_M{m:02d}' for m in range(31)]].resample('D').sum().add_prefix('sum_')], axis=1)
    daily_dataframe = pd.concat([daily_dataframe, hourly_dataframe[[f'wind_speed_10m_M{m:02d}' for m in range(31)]].resample('D').max().add_prefix('max_')], axis=1)
    
    # Create a subplot figure with shared x-axis
    fig = make_subplots(
        rows=4, cols=1,  # Two rows, one column
        shared_xaxes=True,  # Share x-axis across rows
        vertical_spacing=0.05,  # Adjust vertical spacing between plots
        subplot_titles=("Total precipitation [mm/24h]", "Total ET0 FAO evotranspiration [mm/24h]", "10m Wind speed max [m/s]", "2m Temperature min/max [°C]")  # Titles for each subplot
    )

    df = daily_dataframe[[f'sum_precipitation_M{m:02d}' for m in range(1,31)]]
    days = df.index[:16]
    for time in days:
        fig.add_trace(go.Box(
            y=df.loc[time],  # Values for the boxplot (columns at this time point)
            name=str(time.date()),  # Use date as x-axis label
            showlegend=False, 
            marker_color='grey'
            ), row=1, col=1
        )

    df = daily_dataframe[[f'sum_et0_fao_evapotranspiration_M{m:02d}' for m in range(1,31)]]
    for time in days:
        fig.add_trace(go.Box(
            y=df.loc[time],  # Values for the boxplot (columns at this time point)
            name=str(time.date()),  # Use date as x-axis label
            showlegend=False, 
            marker_color='green'
            ), row=2, col=1
        )

    df = daily_dataframe[[f'max_wind_speed_10m_M{m:02d}' for m in range(1,31)]]
    for time in days:
        fig.add_trace(go.Box(
            y=df.loc[time],  # Values for the boxplot (columns at this time point)
            name=str(time.date()),  # Use date as x-axis label
            showlegend=False, 
            marker_color='orange'
            ), row=3, col=1
        )

    df = daily_dataframe[[f'max_temperature_2m_M{m:02d}' for m in range(1,31)]]
    for time in days:
        fig.add_trace(go.Box(
            y=df.loc[time],  # Values for the boxplot (columns at this time point)
            name=str(time.date()),  # Use date as x-axis label
            showlegend=False, 
            marker_color='red'
            ), row=4, col=1
        )

    df = daily_dataframe[[f'min_temperature_2m_M{m:02d}' for m in range(1,31)]]
    for time in days:
        fig.add_trace(go.Box(
            y=df.loc[time],  # Values for the boxplot (columns at this time point)
            name=str(time.date()),  # Use date as x-axis label
            showlegend=False, 
            marker_color='blue'
            ), row=4, col=1
        )

    fig.add_trace(go.Scatter(
        y=daily_dataframe['sum_precipitation_M00'],
        x=days,
        name='control',
        showlegend=False, 
        marker_color='grey'
        ), row=1, col=1
    )

    fig.add_trace(go.Scatter(
        y=daily_dataframe['sum_et0_fao_evapotranspiration_M00'],
        x=days,
        name='control',
        showlegend=False, 
        marker_color='green'
        ), row=2, col=1
    )

    fig.add_trace(go.Scatter(
        y=daily_dataframe['max_wind_speed_10m_M00'],
        x=days,
        name='control',
        showlegend=False, 
        marker_color='orange'
        ), row=3, col=1
    )

    fig.add_trace(go.Scatter(
        y=daily_dataframe['max_temperature_2m_M00'],
        x=days,
        name='control',
        showlegend=False, 
        marker_color='red'
        ), row=4, col=1
    )

    fig.add_trace(go.Scatter(
        y=daily_dataframe['min_temperature_2m_M00'],
        x=days,
        name='control',
        showlegend=False, 
        marker_color='blue'
        ), row=4, col=1
    )

    # Update layout for better visuals
    fig.update_layout(
        title="GFS forecast",
        height=800
    )

    plot_json = json.dumps(fig, cls=PlotlyJSONEncoder)

    return json.loads(plot_json)


@router.get(
    "/ndvi_map",
    summary="Interactive NDVI map with parcels overlay and per-parcel statistics",
    description=(
        "Builds an **interactive Leaflet map** (via Folium) overlaying the latest NDVI GeoTIFF "
        "with a **parcel shapefile**, and computes **zonal statistics** (min/max/mean/std) per parcel.\n\n"
        "**Workflow:**\n"
        "1. Loads the parcel shapefile (`static/shapefiles/parcelle2022_2023.shp`) and reprojects to **EPSG:4326**.\n"
        "2. Scans `static/geotiff_ndvi/` for `.tif` files and selects the **most recent** one.\n"
        "3. Reads the GeoTIFF (NDVI band, transform, nodata, bounds, and metadata tags).\n"
        "4. Computes **zonal stats** on the NDVI array for each parcel: *min*, *max*, *mean*, *std*.\n"
        "5. Renders a Folium map centered on the parcels' centroids, adds an **ImageOverlay** of NDVI (fixed scale 0–1), "
        "and a **GeoJSON** layer with tooltips showing the per-parcel NDVI stats.\n"
        "6. Appends a vertical **colorbar** (0→1) and a **metadata box** (selected GeoTIFF tags).\n\n"
        "Returns an **HTML document** (Leaflet map + overlays) that can be embedded directly in a web page."
    ),
    tags=["NDVI", "Remote Sensing", "Maps"],
    response_description="Embeddable HTML page containing the Leaflet map, NDVI overlay, parcel boundaries, legend, and metadata.",
    responses={
        200: {
            "description": "HTML map successfully generated.",
            "content": {
                "text/html": {
                    "example": "<!doctype html><html><body><div id='map'></div></body></html>"
                }
            }
        },
        404: {"description": "Required input not found (missing shapefile or NDVI GeoTIFF)."},
        503: {"description": "Error while reading geospatial data or generating the map."}
    },
    include_in_schema=True,
    response_class=HTMLResponse,
)
def ndvi_map() -> HTMLResponse:
    """
    Returns an embeddable HTML page with the Leaflet NDVI map and per-parcel statistics.
    See the detailed description above.
    """
    shapefile_path = "static/shapefiles/parcelle2022_2023.shp"
    ndvi_dir = "static/geotiff_ndvi"

    if not os.path.exists(shapefile_path):
        raise fastapi.HTTPException(status_code=404, detail=f"Shapefile non trovato: {shapefile_path}")

    try:
        ndvi_files = sorted(
            [os.path.join(ndvi_dir, f) for f in os.listdir(ndvi_dir) if f.endswith(".tif")]
        )
    except Exception as e:
        raise fastapi.HTTPException(status_code=503, detail=f"Errore nello scanning NDVI: {e}")

    if not ndvi_files:
        raise fastapi.HTTPException(status_code=404, detail=f"Nessun file NDVI trovato in {ndvi_dir}")
    geotiff_path = ndvi_files[-1]

    # --- Load vectors & raster ---
    try:
        polygons = gpd.read_file(shapefile_path).to_crs("EPSG:4326")
    except Exception as e:
        raise fastapi.HTTPException(status_code=503, detail=f"Errore lettura shapefile: {e}")

    try:
        with rasterio.open(geotiff_path) as src:
            array = src.read(1)
            affine = src.transform
            no_data = src.nodata
            bounds = src.bounds
            metadata = src.tags()
    except Exception as e:
        raise fastapi.HTTPException(status_code=503, detail=f"Errore lettura GeoTIFF: {e}")

    # --- Zonal statistics ---
    try:
        stats = zonal_stats(
            polygons, array, affine=affine, nodata=no_data, stats=["min", "max", "mean", "std"]
        )
    except Exception as e:
        raise fastapi.HTTPException(status_code=503, detail=f"Errore calcolo zonal stats: {e}")

    polygons["min_ndvi"] = [s.get("min") for s in stats]
    polygons["max_ndvi"] = [s.get("max") for s in stats]
    polygons["mean_ndvi"] = [s.get("mean") for s in stats]
    polygons["std_ndvi"] = [s.get("std") for s in stats]

    # --- Raster to RGB image with fixed color scale 0–1 ---
    cmap = plt.get_cmap("RdYlGn")
    array_mapped = np.clip(array, 0, 1)  # constrain for color mapping only
    rgba = cmap(array_mapped)
    raster_image = (rgba[:, :, :3] * 255).astype("uint8")
    raster_bounds = [[bounds.bottom, bounds.left], [bounds.top, bounds.right]]

    # --- Map creation ---
    try:
        centroids = polygons.geometry.centroid
        center = [centroids.y.mean(), centroids.x.mean()]
        ndvi_map = folium.Map(location=center, zoom_start=14)

        folium.raster_layers.ImageOverlay(
            image=raster_image,
            bounds=raster_bounds,
            opacity=0.7,
            interactive=True,
        ).add_to(ndvi_map)

        def get_style(_feature):
            return {
                "color": "black",
                "weight": 1.5,
                "fillColor": "#91888800",  # trasparente
                "fillOpacity": 0.0,
            }

        folium.GeoJson(
            polygons.to_json(),
            style_function=get_style,
            tooltip=folium.GeoJsonTooltip(
                fields=["LOCALITà", "TESI", "mean_ndvi", "min_ndvi", "max_ndvi", "std_ndvi"],
                aliases=["Località:", "Tesi:", "NDVI medio:", "NDVI min:", "NDVI max:", "Dev std NDVI:"],
                localize=True,
                labels=True,
                sticky=True,
            ),
        ).add_to(ndvi_map)

        map_html = ndvi_map._repr_html_()
    except Exception as e:
        raise fastapi.HTTPException(status_code=503, detail=f"Errore generazione mappa: {e}")

    # --- Colorbar ---
    n_ticks = 11
    tick_vals = np.linspace(0, 1, n_ticks)
    colormap = plt.get_cmap("RdYlGn")
    colors = [mcolors.to_hex(colormap(v)) for v in np.linspace(0, 1, 256)]
    gradient_css = ", ".join(colors)

    colorbar_vertical = f"""
    <div style="
        position: absolute;
        top: 80px;
        right: 20px;
        width: 110px;
        height: 600px;
        background-color: white;
        padding: 10px 10px 10px 10px;
        border: 1px solid #ccc;
        display: flex;
        flex-direction: row;
        align-items: center;
        z-index: 9999;
    ">
        <div style='width: 35px; height: 100%;
            background: linear-gradient(to top, {gradient_css});
            border: 1px solid #ccc;'>
        </div>
        <div style="
            margin-left: 12px;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            font-size: 0.9rem;
        ">
    """
    for val in reversed(tick_vals):
        colorbar_vertical += f"<div style='text-align: left;'>{val:.2f}</div>"
    colorbar_vertical += "</div></div>"

    # --- Metadata box ---
    keys = ["AREA_NAME", "SENSOR_TYPE", "DESCRIPTION", "ACQUISITION_DATETIME", "PROCESSING_VERSION"]
    metadata_html = """
    <div class="box" style="margin-top: 1.5rem;">
      <h4 class="title is-5">NDVI Metadata</h4>
      <div class="content">
        <dl>
    """
    for key in keys:
        if key in metadata:
            metadata_html += f"<dt>{key.replace('_', ' ').title()}</dt><dd>{metadata[key]}</dd>"
    metadata_html += """
        </dl>
      </div>
    </div>
    """

    return HTMLResponse(content=map_html + colorbar_vertical + metadata_html)


def download_and_save_new_ndvi_scl(
    client_id,
    client_secret,
    bbox_coords,
    time_interval,
    ndvi_dir,
    scl_dir,
    resolution=10,
    max_cloud_cover=100
):
    os.makedirs(ndvi_dir, exist_ok=True)
    os.makedirs(scl_dir, exist_ok=True)

    config = SHConfig()
    config.sh_client_id = client_id
    config.sh_client_secret = client_secret
    config.sh_token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    config.sh_base_url = "https://sh.dataspace.copernicus.eu"

    bbox = BBox(bbox=bbox_coords, crs=CRS.WGS84)
    size = bbox_to_dimensions(bbox, resolution=resolution)

    catalog = SentinelHubCatalog(config=config)
    search_iterator = catalog.search(
        DataCollection.SENTINEL2_L2A,
        bbox=bbox,
        time=time_interval,
        filter=f"eo:cloud_cover <= {max_cloud_cover}",
        fields={"include": ["id", "properties.datetime", "properties.eo:cloud_cover"], "exclude": []},
    )

    all_timestamps = search_iterator.get_timestamps()
    time_difference = timedelta(hours=1)
    unique_acquisitions = filter_times(all_timestamps, time_difference)

    evalscript_ndvi = """
    //VERSION=3
    function setup() {
        return {
            input: ["B04", "B08", "dataMask"],
            output: [
                { id: "index", bands: 1, sampleType: "FLOAT32" },
                { id: "dataMask", bands: 1 }
            ]
        };
    }
    function evaluatePixel(samples) {
        let ndvi = index(samples.B08, samples.B04);
        let masked = samples.dataMask === 1 ? ndvi : NaN;
        return {
            index: [masked],
            dataMask: [samples.dataMask]
        };
    }"""

    evalscript_scl = """
    //VERSION=3
    function setup() {
        return {
            input: ["SCL"],
            output: { bands: 1, sampleType: "UINT8" }
        };
    }
    function evaluatePixel(samples) {
        return [samples.SCL];
    }"""

    for timestamp in unique_acquisitions:
        ts_str = timestamp.strftime("%Y%m%dT%H%M%S")
        out_path_ndvi = os.path.join(ndvi_dir, f"ndvi_{ts_str}.tif")
        out_path_scl = os.path.join(scl_dir, f"scl_{ts_str}.tif")

        # Salta se entrambi i file esistono
        if os.path.exists(out_path_ndvi) and os.path.exists(out_path_scl):
            continue

        # === NDVI ===
        request_ndvi = SentinelHubRequest(
            evalscript=evalscript_ndvi,
            input_data=[
                SentinelHubRequest.input_data(
                    data_collection=DataCollection.SENTINEL2_L2A.define_from("s2l2a", service_url=config.sh_base_url),
                    time_interval=(timestamp - time_difference, timestamp + time_difference)
                )
            ],
            responses=[SentinelHubRequest.output_response("index", MimeType.TIFF)],
            bbox=bbox,
            size=size,
            config=config,
        )
        array_ndvi = request_ndvi.get_data()[0]
        transform = from_bounds(*bbox_coords, width=size[0], height=size[1])
        metadata_ndvi = {
            "driver": "GTiff",
            "dtype": rasterio.float32,
            "count": 1,
            "width": array_ndvi.shape[1],
            "height": array_ndvi.shape[0],
            "crs": "EPSG:4326",
            "transform": transform,
            "nodata": np.nan
        }
        with rasterio.open(out_path_ndvi, "w", **metadata_ndvi) as dst:
            dst.write(array_ndvi.astype(np.float32), 1)
            dst.update_tags(
                ACQUISITION_DATETIME=timestamp.isoformat(),
                SENSOR_TYPE="Sentinel-2 L2A",
                AREA_NAME=f"{bbox_coords}",
                DESCRIPTION="NDVI derived from Sentinel-2 (B08/B04)",
                PROCESSING_VERSION="1.0",
                RESOLUTION=str(resolution),
                CLOUD_COVER=str(max_cloud_cover)
            )

        # === SCL ===
        request_scl = SentinelHubRequest(
            evalscript=evalscript_scl,
            input_data=[
                SentinelHubRequest.input_data(
                    data_collection=DataCollection.SENTINEL2_L2A.define_from("s2l2a", service_url=config.sh_base_url),
                    time_interval=(timestamp - time_difference, timestamp + time_difference)
                )
            ],
            responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
            bbox=bbox,
            size=size,
            config=config,
        )
        array_scl = request_scl.get_data()[0]
        metadata_scl = {
            "driver": "GTiff",
            "dtype": rasterio.uint8,
            "count": 1,
            "width": array_scl.shape[1],
            "height": array_scl.shape[0],
            "crs": "EPSG:4326",
            "transform": transform,
            "nodata": None
        }
        with rasterio.open(out_path_scl, "w", **metadata_scl) as dst:
            dst.write(array_scl.astype(np.uint8), 1)
            dst.update_tags(
                ACQUISITION_DATETIME=timestamp.isoformat(),
                DESCRIPTION="Scene Classification Layer (SCL) from Sentinel-2",
                PROCESSING_VERSION="1.0"
            )

        print(f"✔ Saved NDVI: {out_path_ndvi}")
        print(f"✔ Saved SCL:  {out_path_scl}")


def extract_ndvi_series_grouped_by_treatment_valid_classes(
    shapefile_path,
    ndvi_dir,
    scl_dir,
    location_column="LOCALITà",
    treatment_column="TESI",
    valid_classes={4, 5}
):
    if not os.path.exists(shapefile_path):
        raise FileNotFoundError(f"Shapefile non trovato: {shapefile_path}")
    
    polygons = gpd.read_file(shapefile_path).to_crs("EPSG:4326")
    if location_column not in polygons.columns or treatment_column not in polygons.columns:
        raise ValueError("Colonne richieste non trovate nello shapefile")

    polygons["GROUP"] = (
        polygons[location_column].astype(str).str.upper().str.strip() + "_" +
        polygons[treatment_column].astype(str).str.strip()
    )

    ndvi_files = sorted([f for f in os.listdir(ndvi_dir) if f.endswith(".tif")])
    scl_files = sorted([f for f in os.listdir(scl_dir) if f.endswith(".tif")])

    if len(ndvi_files) != len(scl_files):
        raise ValueError("Numero di file NDVI e SCL non corrisponde")

    records = []
    for ndvi_file, scl_file in zip(ndvi_files, scl_files):
        ndvi_path = os.path.join(ndvi_dir, ndvi_file)
        scl_path = os.path.join(scl_dir, scl_file)

        with rasterio.open(ndvi_path) as ndvi_src, rasterio.open(scl_path) as scl_src:
            metadata = ndvi_src.tags()
            raw_date = metadata.get("ACQUISITION_DATETIME", None)
            label = None
            if raw_date:
                try:
                    label = datetime.fromisoformat(raw_date)
                except Exception:
                    pass
            if label is None:
                try:
                    label = pd.to_datetime(Path(ndvi_file).stem, errors="coerce")
                except Exception:
                    continue
            if label is None or pd.isna(label):
                continue

            group_values = {}
            for idx, row in polygons.iterrows():
                group = row["GROUP"]
                geom = [mapping(row.geometry)]
                try:
                    ndvi_masked, _ = mask(ndvi_src, geom, crop=True)
                    scl_masked, _ = mask(scl_src, geom, crop=True)
                except Exception:
                    continue

                ndvi_vals = ndvi_masked[0]
                scl_vals = scl_masked[0]

                valid_mask = (~np.isnan(ndvi_vals)) & (np.isin(scl_vals, list(valid_classes)))
                if np.any(valid_mask):
                    mean_val = float(np.nanmean(ndvi_vals[valid_mask]))
                else:
                    mean_val = np.nan

                if group not in group_values:
                    group_values[group] = []
                group_values[group].append(mean_val)

            aggregated = {
                g: np.nanmean(vals) if len(vals) > 0 and not all(np.isnan(vals)) else np.nan
                for g, vals in group_values.items()
            }
            records.append((label, aggregated))

    df = pd.DataFrame.from_records(
        [r[1] for r in records],
        index=[r[0] for r in records]
    )
    df.index.name = "timestamp"
    df = df.sort_index()
    return df


@router.get(
    "/precipitation_plot/{latitude}/{longitude}",
    summary="Daily precipitation (Open-Meteo) with NDVI time-series (Sentinel-2) by treatment",
    description=(
        "Builds a **dual-axis Plotly chart** combining daily **precipitation** from the "
        "**Open-Meteo Archive API** with **NDVI time-series** extracted from Sentinel-2 over a fixed AOI.\n\n"
        "**Workflow:**\n"
        "1. Queries `https://archive-api.open-meteo.com/v1/archive` for *daily* `precipitation_sum` using "
        "*latitude* and *longitude*, from **2022-10-01** to **today** (`models=best_match`).\n"
        "2. Calls an internal routine `download_and_save_new_ndvi_scl(...)` to **download any new Sentinel-2 scenes** "
        "(NDVI & SCL) inside a fixed bounding box (10 m resolution, cloud cover ≤ 40%).\n"
        "3. Extracts NDVI time-series grouped by treatment with "
        "`extract_ndvi_series_grouped_by_treatment_valid_classes(...)` using "
        "`static/shapefiles/parcelle2022_2023.shp`.\n"
        "4. Creates a Plotly figure with **precipitation** (primary y-axis) and **NDVI** per treatment "
        "(secondary y-axis), and returns the **figure as JSON** suitable for `Plotly.newPlot(...)`."
    ),
    tags=["NDVI", "Precipitation", "Open-Meteo", "Sentinel-2"],
    response_description="Plotly figure serialized as JSON with precipitation and NDVI lines.",
    responses={
        200: {
            "description": "Figure successfully generated (Plotly JSON).",
            "content": {
                "application/json": {
                    "example": {
                        "data": [
                            {"type": "scatter", "name": "Precipitation", "y": [0.6, 3.2, 0.0]},
                            {"type": "scatter", "name": "Ussana 100%", "y": [0.41, 0.56, 0.52]}
                        ],
                        "layout": {"title": "Precipitation and NDVI"}
                    }
                }
            }
        },
        404: {"description": "Shapefile not found."},
        422: {"description": "Invalid parameters (lat/long out of range, wrong types)."},
        503: {"description": "Upstream service or geospatial processing error."}
    },
    include_in_schema=True,
    response_class=JSONResponse,
)
async def precipitation_plot(
    latitude: float = fastapi.Path(..., ge=-90, le=90, description="Latitude in decimal degrees (−90 … +90)."),
    longitude: float = fastapi.Path(..., ge=-180, le=180, description="Longitude in decimal degrees (−180 … +180).")
) -> dict:
    """
    Returns the Plotly figure as JSON. See the detailed description above.
    """
    # === 1) Open-Meteo: daily precipitation ===
    try:
        cache_session = requests_cache.CachedSession(".cache", expire_after=-1)
        retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        openmeteo = openmeteo_requests.Client(session=retry_session)

        start_date = "2022-10-01"
        today = datetime.today().strftime("%Y-%m-%d")
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": today,
            "daily": "precipitation_sum",
            "models": "best_match",
        }
        responses = openmeteo.weather_api(url, params=params)
        response = responses[0]
        daily = response.Daily()

        daily_precipitation_sum = daily.Variables(0).ValuesAsNumpy()
        daily_data = {
            "date": pd.date_range(
                start=pd.to_datetime(daily.Time(), unit="s", utc=True),
                end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
                freq=pd.Timedelta(seconds=daily.Interval()),
                inclusive="left",
            ),
            "precipitation_sum": daily_precipitation_sum,
        }
        daily_dataframe = pd.DataFrame(daily_data).set_index("date")
    except Exception as e:
        raise fastapi.HTTPException(status_code=503, detail=f"Open-Meteo error: {e}")

    # === 2) Sentinel-2 NDVI/SCL: download missing scenes ===
    try:
        # Fixed AOI bounding box (minLon, minLat, maxLon, maxLat)
        bbox_coords = (9.0747, 39.4022, 9.1186, 39.4361)
        time_interval = (start_date, today)

        client_id = os.getenv("SH_CLIENT_ID")
        client_secret = os.getenv("SH_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise RuntimeError("Sentinel Hub credentials missing (set SH_CLIENT_ID and SH_CLIENT_SECRET).")

        ndvi_dir = "static/geotiff_ndvi"
        scl_dir = "static/geotiff_scl"

        download_and_save_new_ndvi_scl(
            client_id=client_id,
            client_secret=client_secret,
            bbox_coords=bbox_coords,
            time_interval=time_interval,
            ndvi_dir=ndvi_dir,
            scl_dir=scl_dir,
            resolution=10,
            max_cloud_cover=40,
        )
    except Exception as e:
        raise fastapi.HTTPException(status_code=503, detail=f"Sentinel-2 download error: {e}")

    # === 3) NDVI extraction grouped by treatment ===
    try:
        shapefile_path = "static/shapefiles/parcelle2022_2023.shp"
        if not os.path.exists(shapefile_path):
            raise fastapi.HTTPException(status_code=404, detail=f"Shapefile non trovato: {shapefile_path}")

        df_ndvi = extract_ndvi_series_grouped_by_treatment_valid_classes(
            shapefile_path=shapefile_path, ndvi_dir=ndvi_dir, scl_dir=scl_dir
        )
    except fastapi.HTTPException:
        raise
    except Exception as e:
        raise fastapi.HTTPException(status_code=503, detail=f"NDVI extraction error: {e}")

    group_names = [
        ("BENATZU_TEST", "Benatzu Test", "Blugrn"),
        ("BENATZU_50", "Benatzu 50%", "Blugrn"),
        ("BENATZU_100", "Benatzu 100%", "Blugrn"),
        ("USSANA_TEST", "Ussana Test", "Redor"),
        ("USSANA_50", "Ussana 50%", "Redor"),
        ("USSANA_100", "Ussana 100%", "Redor"),
    ]

    # === 4) Plotly figure ===
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=daily_dataframe.index,
            y=daily_dataframe["precipitation_sum"],
            name="Precipitation",
            mode="lines+markers",
            line_color="darkblue",
        ),
        secondary_y=False,
    )

    # Color NDVI lines by treatment using Plotly colorscales
    for i, (group_col, label, colorscale) in enumerate(group_names):
        if group_col not in df_ndvi.columns:
            continue
        s = df_ndvi[group_col].dropna()
        if s.empty:
            continue
        color = sample_colorscale(colorscale, [i / max(1, len(group_names) - 1)])[0]
        fig.add_trace(
            go.Scatter(x=s.index, y=s, name=label, mode="lines+markers", line_color=color),
            secondary_y=True,
        )

    fig.update_layout(title="Precipitation and NDVI", height=800)
    fig.update_xaxes(title_text="Date")
    fig.update_yaxes(title_text="Precipitation [mm H₂O]", secondary_y=False)
    fig.update_yaxes(title_text="NDVI [-]", secondary_y=True)

    return json.loads(json.dumps(fig, cls=PlotlyJSONEncoder))


# -------------------------------
# 1) Run AquaCrop simulation
# -------------------------------
@router.post(
    "/simulation",
    summary="Run AquaCrop simulation from uploaded weather file (Ussana/Benatzu)",
    description=(
        "Uploads a weather input file and runs the **AquaCrop** model for the selected site "
        "(**Ussana** or **Benatzu**), then returns a **Plotly figure JSON** and a **download URL** "
        "for detailed results.\n"
        "Optional irr (0–100) controls support irrigation via AquaCrop’s IrrigationManagement (SMT). When irr=0, irrigation is disabled.\n\n"
        "**Workflow:**\n"
        "1. Accepts a multipart form with a file (`file`) and a site selection (`site`).\n"
        "2. Saves the uploaded file under `uploads/`.\n"
        "3. Runs `aquacrop_run_ussana(...)` or `aquacrop_run_benatzu(...)` based on `site`.\n"
        "4. Extracts `model._outputs.final_stats` and saves it as JSON (`*_results.json`) in `uploads/`.\n"
        "5. Builds a Plotly figure with **Yield potential** and **Fresh yield** vs. **Harvest Date (YYYY/MM/DD)**.\n"
        "6. Returns the Plotly **figure JSON** and a `download_url` pointing to `/download/{filename}`."
    ),
    tags=["AquaCrop", "Simulation"],
    response_description="Plotly figure as JSON and a URL to download the full results JSON.",
    responses={
        200: {
            "description": "Simulation completed; figure and download URL returned.",
            "content": {
                "application/json": {
                    "example": {
                        "plot": {
                            "data": [
                                {"type": "scatter", "name": "Yield potential", "mode": "lines+markers"},
                                {"type": "scatter", "name": "Fresh yield", "mode": "lines+markers"}
                            ],
                            "layout": {"title": "Ussana production"}
                        },
                        "download_url": "/download/example_results.json"
                    }
                }
            }
        },
        400: {"description": "Invalid `site` value."},
        422: {"description": "Validation error (missing file or form fields)."},
        503: {"description": "Simulation failed (AquaCrop error)."}
    },
    include_in_schema=True,
    response_class=JSONResponse,
)
async def process_file(
    request: Request,
    file: fastapi.UploadFile = fastapi.File(..., description="Weather input file for AquaCrop."),
    site: str = fastapi.Form(..., description="Target site: 'Ussana' or 'Benatzu'."),
    irr: Annotated[int, fastapi.Form(ge=0, le=100, description="Support irrigation (%) 0–100.")] = 0,
) -> dict:
    """
    Returns a Plotly figure JSON and a download URL for the results JSON.
    """
    # Ensure uploads dir exists
    os.makedirs("uploads", exist_ok=True)

    # Save file
    file_path = os.path.join("uploads", file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    # Run simulation
    try:
        if site == "Ussana":
            model = aquacrop_run_ussana(file_path, irr)
        elif site == "Benatzu":
            model = aquacrop_run_benatzu(file_path, irr)
        else:
            return JSONResponse({"error": "Invalid site. Use 'Ussana' or 'Benatzu'."}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": f"AquaCrop simulation failed: {e}"}, status_code=503)

    df = model._outputs.final_stats

    # Save results JSON
    json_filename = f"{file.filename}_results.json"
    json_filepath = os.path.join("uploads", json_filename)
    df.to_json(json_filepath, orient="records", date_format="iso")

    # Build figure
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['Harvest Date (YYYY/MM/DD)'],
        y=df['Yield potential (tonne/ha)'],
        mode="lines+markers",
        name="Yield potential",
        showlegend=False
    ))
    fig.add_trace(go.Scatter(
        x=df['Harvest Date (YYYY/MM/DD)'],
        y=df['Fresh yield (tonne/ha)'],
        mode="lines+markers",
        name="Fresh yield",
        showlegend=False
    ))
    fig.update_layout(
        title=f"{site} production",
        xaxis_title="Year",
        yaxis_title="Yield (tonne/ha)",
        xaxis_showgrid=True,
        yaxis_showgrid=True,
        height=500
    )

    return {
        "plot": json.loads(json.dumps(fig, cls=PlotlyJSONEncoder)),
        "download_url": f"/download/{json_filename}"
    }


# -------------------------------
# 2) Download results file
# -------------------------------
@router.get(
    "/download/{filename}",
    summary="Download a results JSON produced by /simulation",
    description=(
        "Serves a JSON file previously generated by the **/simulation** endpoint. "
        "The file must exist under `uploads/`."
    ),
    tags=["AquaCrop", "Simulation"],
    response_description="Raw JSON file with simulation statistics.",
    responses={
        200: {
            "description": "File found and returned.",
            "content": {
                "application/json": {
                    "example": [
                        {"Harvest Date (YYYY/MM/DD)": "2025/06/30",
                         "Yield potential (tonne/ha)": 5.1,
                         "Fresh yield (tonne/ha)": 8.4}
                    ]
                }
            }
        },
        404: {"description": "File not found."}
    },
    include_in_schema=True,
    response_model=None,  # <- avoid Pydantic model generation
)
async def download_file(filename: str) -> fastapi.Response:  # <- annotate as Response
    file_path = os.path.join("uploads", filename)
    if not os.path.exists(file_path):
        raise fastapi.HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type="application/json", filename=filename)


# -------------------------------
# 3) Simple upload helper
# -------------------------------
@router.post(
    "/upload/",
    summary="Upload a file to the server (utility endpoint)",
    description=(
        "Uploads a file and stores it under `uploads/`. "
        "Primarily used as a helper to pre-stage inputs."
    ),
    tags=["Utilities"],
    response_description="Echoes filename and server-side path.",
    responses={
        200: {
            "description": "Upload completed.",
            "content": {
                "application/json": {
                    "example": {"filename": "weather.txt", "filepath": "uploads/weather.txt"}
                }
            }
        },
        422: {"description": "Validation error (missing file)."}
    },
    include_in_schema=True,
)
async def upload_file(file: fastapi.UploadFile = fastapi.File(..., description="Any file to store under uploads/")):
    os.makedirs("uploads", exist_ok=True)
    file_path = os.path.join("uploads", file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
    return {"filename": file.filename, "filepath": file_path}


# -------------------------------
# 4) Water profile (AquaCrop ensemble)
# -------------------------------
@router.get(
    "/water_profile",
    summary="Generate (or reuse) AquaCrop ensemble water-profile plots for a location",
    description=(
        "Runs (or reuses cached) **AquaCrop ensemble** simulations and returns URLs to two PNG images:\n"
        "- **Water profile quantiles** (soil water content by layer, ensemble bands)\n"
        "- **Model outputs overview** (ensemble quantiles for key variables)\n\n"
        "**Workflow:**\n"
        "1. Based on `location` (**Ussana** or **Benatzu**), selects the site coordinates.\n"
        "2. Retrieves historical + ensemble forecast weather (Open-Meteo GFS seamless).\n"
        "3. If daily/ensemble CSVs for **today** exist in `static/data/`, they are reused (cache).\n"
        "4. Runs AquaCrop across ensemble members and saves two PNGs under `static/png/`.\n"
        "5. Returns the relative URLs of the two images.\n\n"
        "Set `force=true` to recompute even if cached files exist."
    ),
    tags=["AquaCrop", "Ensemble", "Water Profile"],
    response_description="JSON with URLs to two PNG images.",
    responses={
        200: {
            "description": "Images generated or retrieved from cache.",
            "content": {
                "application/json": {
                    "example": {
                        "image_url_1": "/static/png/water_profile_quantiles_Ussana_20250819.png",
                        "image_url_2": "/static/png/model_outputs_Ussana_20250819.png"
                    }
                }
            }
        },
        400: {"description": "Unsupported location."},
        503: {"description": "Upstream data error or model failure."}
    },
    include_in_schema=True,
)
def water_profile(
    location: Annotated[str, fastapi.Query(description="Target site: 'Ussana' or 'Benatzu'.")] = "Ussana",
    irr: Annotated[int, fastapi.Query(ge=0, le=100, description="Support irrigation (%) 0–100.")] = 0,
    force: Annotated[bool, fastapi.Query(description="Recompute even if cached.")] = False,
) -> dict:
    """
    Returns two image URLs (PNG) saved under static/png/.
    """
    try:
        image_path_1, image_path_2 = run_ensemble_and_generate_plot(location, force=force, irr=irr)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": f"Water profile generation failed: {e}"}, status_code=503)

    return {"image_url_1": f"/{image_path_1}", "image_url_2": f"/{image_path_2}"}
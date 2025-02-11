import fastapi
from starlette.requests import Request
from starlette.templating import Jinja2Templates
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse, FileResponse
from fastapi import Form, File, UploadFile, HTTPException
import requests
from io import BytesIO
from PIL import Image
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from plotly.utils import PlotlyJSONEncoder
from plotly.express.colors import sample_colorscale
import json
import pandas as pd
from sklearn.preprocessing import minmax_scale
import os

from models.aquacrop_model import aquacrop_run_ussana, aquacrop_run_benatzu
from models.mistral_model import get_total_dataframe

import openmeteo_requests
from openmeteo_sdk.Variable import Variable
from openmeteo_sdk.Aggregation import Aggregation
import requests_cache
from retry_requests import retry

import folium
import geopandas as gpd
import rasterio
import matplotlib.pyplot as plt
import matplotlib.cm
import matplotlib.colors as mcolors
from rasterstats import zonal_stats

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

#@router.get('/loaderio-5b231ba7b420bdcc2e5b2aaf785f7201.txt', response_class=PlainTextResponse, include_in_schema=False)
#def loaderio():
#    return "loaderio-5b231ba7b420bdcc2e5b2aaf785f7201"

@router.get("/ecmwf_forecast/{station}", include_in_schema=False)
async def ecmwf_forecast(
    station: str
    ):
    # URL of the JSON endpoint
    if station == 'Ussana':
        lat = 39.3919
        lon = 9.0775
    else:
        lat = 39.3919
        lon = 9.0775
    
    json_url = f"https://charts.ecmwf.int/opencharts-api/v1/products/opencharts_meteogram/?epsgram=classical_15d_with_climate&station_name={station}&lat={lat}&lon={lon}"

    try:
        # Fetch the JSON data
        response = requests.get(json_url)
        response.raise_for_status()
        json_data = response.json()
        
        # Extract the PNG URL from the JSON structure
        png_url = json_data.get("data", {}).get("link", {}).get("href")
        if not png_url:
            raise ValueError("No 'href' field found in the JSON under 'data -> link'.")
        
        # Fetch the PNG image
        image_response = requests.get(png_url)
        image_response.raise_for_status()
        image = Image.open(BytesIO(image_response.content))
        
        # Define the bounding boxes for the two portions (adjust as needed)
        # Portion 1
        crop_box1 = (0, 200, image.width, 316)  # Full width, adjust height
        cropped_image1 = image.crop(crop_box1)
        
        # Portion 2
        crop_box2 = (0, 450, image.width, 700)  # Full width, adjust height #684-700
        cropped_image2 = image.crop(crop_box2)
        
        # Create a new image with combined height
        combined_height = cropped_image1.height + cropped_image2.height
        combined_image = Image.new("RGB", (image.width, combined_height))
        
        # Paste the two cropped portions into the new image
        combined_image.paste(cropped_image1, (0, 0))  # First crop at the top
        combined_image.paste(cropped_image2, (0, cropped_image1.height))  # Second crop below the first
        
        buf = BytesIO()
        combined_image.save(buf, format="PNG")
        buf.seek(0)
        
        return StreamingResponse(buf, media_type="image/png")
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None
    except ValueError as e:
        print(e)
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

@router.get("/gfs_forecast/{latitude}/{longitude}", include_in_schema=False)
async def gfs_forecast(latitude: float, longitude: float):
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
    for time in df.index:
        fig.add_trace(go.Box(
            y=df.loc[time],  # Values for the boxplot (columns at this time point)
            name=str(time.date()),  # Use date as x-axis label
            showlegend=False, 
            marker_color='grey'
            ), row=1, col=1
        )

    df = daily_dataframe[[f'sum_et0_fao_evapotranspiration_M{m:02d}' for m in range(1,31)]]
    for time in df.index:
        fig.add_trace(go.Box(
            y=df.loc[time],  # Values for the boxplot (columns at this time point)
            name=str(time.date()),  # Use date as x-axis label
            showlegend=False, 
            marker_color='green'
            ), row=2, col=1
        )

    df = daily_dataframe[[f'max_wind_speed_10m_M{m:02d}' for m in range(1,31)]]
    for time in df.index:
        fig.add_trace(go.Box(
            y=df.loc[time],  # Values for the boxplot (columns at this time point)
            name=str(time.date()),  # Use date as x-axis label
            showlegend=False, 
            marker_color='orange'
            ), row=3, col=1
        )

    df = daily_dataframe[[f'max_temperature_2m_M{m:02d}' for m in range(1,31)]]
    for time in df.index:
        fig.add_trace(go.Box(
            y=df.loc[time],  # Values for the boxplot (columns at this time point)
            name=str(time.date()),  # Use date as x-axis label
            showlegend=False, 
            marker_color='red'
            ), row=4, col=1
        )

    df = daily_dataframe[[f'min_temperature_2m_M{m:02d}' for m in range(1,31)]]
    for time in df.index:
        fig.add_trace(go.Box(
            y=df.loc[time],  # Values for the boxplot (columns at this time point)
            name=str(time.date()),  # Use date as x-axis label
            showlegend=False, 
            marker_color='blue'
            ), row=4, col=1
        )

    fig.add_trace(go.Scatter(
        y=daily_dataframe['sum_precipitation_M00'],
        x=df.index,
        name='control',
        showlegend=False, 
        marker_color='grey'
        ), row=1, col=1
    )

    fig.add_trace(go.Scatter(
        y=daily_dataframe['sum_et0_fao_evapotranspiration_M00'],
        x=df.index,
        name='control',
        showlegend=False, 
        marker_color='green'
        ), row=2, col=1
    )

    fig.add_trace(go.Scatter(
        y=daily_dataframe['max_wind_speed_10m_M00'],
        x=df.index,
        name='control',
        showlegend=False, 
        marker_color='orange'
        ), row=3, col=1
    )

    fig.add_trace(go.Scatter(
        y=daily_dataframe['max_temperature_2m_M00'],
        x=df.index,
        name='control',
        showlegend=False, 
        marker_color='red'
        ), row=4, col=1
    )

    fig.add_trace(go.Scatter(
        y=daily_dataframe['min_temperature_2m_M00'],
        x=df.index,
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

    
@router.get("/prec_plot/{station}", include_in_schema=False)
def mistral_p(
    station: str
    ):

    # Create a figure with secondary Y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    df_prec = get_total_dataframe()
    
    col = 'darkblue' #aqua, aquamarine, azure, cadetblue, darkblue
    lab = 'Prec.'
    s = df_prec['Prec']
    s = s.dropna()
    fig.add_trace(
        go.Scatter(x=s.dropna().index, y=s.dropna(), 
                   name=lab, mode='lines+markers', line_color=col, showlegend=False
                  ),
        secondary_y=False
        )
    
    colors_ = range(12//4)
    benatzu_colors = sample_colorscale('Blugrn', minmax_scale(colors_))
    ussana_colors = sample_colorscale('Redor', minmax_scale(colors_))
    
    for idx in range(24):
        field = f'field_{idx}'
        if (idx // 4) == 0 :
            col = benatzu_colors[idx // 4]
            lab = f'B test {idx % 4 +1}'
        if (idx // 4) == 1 :
            col = benatzu_colors[idx // 4]
            lab = f'B 50% {idx % 4 +1}'
        if (idx // 4) == 2 :
            col = benatzu_colors[idx // 4]
            lab = f'B 100% {idx % 4 +1}'
        if (idx // 4) == 3 :
            col = ussana_colors[idx // 4 - 3]
            lab = f'U test {idx % 4 +1}'
        if (idx // 4) == 4 :
            col = ussana_colors[idx // 4 - 3]
            lab = f'U 50% {idx % 4 +1}'
        if (idx // 4) == 5 :
            col = ussana_colors[idx // 4 - 3]
            lab = f'U 100% {idx % 4 +1}'
    
        s = df_prec[field]
        s = s.dropna()
        fig.add_trace(
            go.Scatter(x=s.dropna().index, y=s.dropna(), 
                       name=lab, mode='lines+markers', line_color=col, showlegend=False
                      ),
            secondary_y=True
            )
    
    # Add figure title
    fig.update_layout(
        title="Precipitation and NDVI",
        height=800
    )
    
    # Set x-axis title
    fig.update_xaxes(title_text="date")
    
    # Set y-axes titles
    fig.update_yaxes(title_text="precipitation [mm H2O]", secondary_y=False)
    fig.update_yaxes(title_text="NDVI [-]", secondary_y=True)
    plot_json = json.dumps(fig, cls=PlotlyJSONEncoder)

    return json.loads(plot_json)
    
@router.post("/simulation", response_class=HTMLResponse)
async def process_file(
    request: Request,
    file: UploadFile = File(...),  # File upload
    site: str = Form(...)     # Parameter selected by radio buttons
):
    # Save the uploaded file to a temporary location
    file_path = os.path.join('uploads', file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
    print(file_path)

    # Perform simulation
    if site == "Ussana":
        print(file_path)
        model = aquacrop_run_ussana(file_path)
    elif site == "Benatzu":
        model = aquacrop_run_benatzu(file_path)
    
    df = model._outputs.final_stats
    print(df.head())

    # Create a Plotly figure
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['Harvest Date (YYYY/MM/DD)'], 
                             y=df['Yield potential (tonne/ha)'], 
                             mode="lines+markers", name="Yield potential", showlegend=False))
    fig.add_trace(go.Scatter(x=df['Harvest Date (YYYY/MM/DD)'], 
                             y=df['Fresh yield (tonne/ha)'], 
                             mode="lines+markers", name="Fresh yield", showlegend=False))
    fig.update_layout(title=f"{site} production", 
                      xaxis_title="Year", yaxis_title="Yield (tonne/ha)",
                      xaxis_showgrid=True, yaxis_showgrid=True, 
                      height=500)
    
    # Serialize the figure using PlotlyJSONEncoder
    fig_json = json.dumps(fig, cls=PlotlyJSONEncoder)

    # Save JSON file for download
    json_filename = f"{site}_simulation_results.json"
    json_filepath = os.path.join('downloads', json_filename)
    with open(json_filepath, "w") as json_file:
        json.dump(fig, json_file)

    # Return JSON response with download link
    return {
        "plot": json.loads(fig_json),
        "download_url": f"/download/{json_filename}"
    }

@router.get("/download/{filename}")
async def download_file(filename: str):
    file_path = os.path.join('downloads', filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename, media_type="application/json")
    return JSONResponse(content={"error": "File not found"}, status_code=404)

@router.get("/ndvi_map", include_in_schema=False, response_class=HTMLResponse)
async def prepare_map():
    # Percorsi ai file
    shapefile_path = "static/shapefiles/parcelle2022_2023.shp"
    geotiff_path = "static/geotiff/ndvi_geotiff.tif"

    # Carica i poligoni
    polygons = gpd.read_file(shapefile_path)
    polygons = polygons.to_crs("EPSG:4326")  # Assicura che sia in EPSG:4326

    # Calcola le statistiche NDVI per ciascun poligono
    with rasterio.open(geotiff_path) as src:
        affine = src.transform
        array = src.read(1)  # NDVI values
        no_data = src.nodata

    stats = zonal_stats(
        polygons,
        array,
        affine=affine,
        nodata=no_data,
        stats=["min", "max", "mean", "std"],
    )

    # Aggiungi le statistiche ai poligoni
    polygons["min_ndvi"] = [stat["min"] for stat in stats]
    polygons["max_ndvi"] = [stat["max"] for stat in stats]
    polygons["mean_ndvi"] = [stat["mean"] for stat in stats]
    polygons["std_ndvi"] = [stat["std"] for stat in stats]

    # Load NDVI raster map
    with rasterio.open(geotiff_path) as src:
        raster_data = src.read(1)
        bounds = src.bounds

    # Normalize raster for visualization
    raster_min, raster_max = raster_data.min(), raster_data.max()
    raster_normalized = (raster_data - raster_min) / (raster_max - raster_min)
    raster_image = matplotlib.cm.viridis(raster_normalized)
    raster_image = (raster_image[:, :, :3] * 255).astype("uint8")

    # Extract raster geographic bounds
    raster_bounds = [[bounds.bottom, bounds.left], [bounds.top, bounds.right]]

    # Create map centered on the polygon domain
    projected_polygons = polygons.to_crs(epsg=3857)  # Convert to projected CRS for centroids
    centroids = projected_polygons.geometry.centroid.to_crs(epsg=4326)
    center = [centroids.y.mean(), centroids.x.mean()]
    ndvi_map = folium.Map(location=center, zoom_start=14)

    # Add raster map as background
    folium.raster_layers.ImageOverlay(
        image=raster_image,
        bounds=raster_bounds,
        opacity=0.7,
        interactive=True,
    ).add_to(ndvi_map)

    # Convert the GeoDataFrame to GeoJSON (keeps all properties)
    geojson_data = polygons.to_json()

    # Define colormap for NDVI values based on raster range
    norm = mcolors.Normalize(vmin=raster_min, vmax=raster_max)
    cmap = plt.get_cmap("viridis")

    def get_style(feature):
        """Style function to dynamically set fillColor based on NDVI mean."""
        ndvi_value = feature["properties"].get("mean_ndvi", raster_min)  # Default to raster_min if missing
        normalized_ndvi = (ndvi_value - raster_min) / (raster_max - raster_min)
        normalized_ndvi = max(0, min(1, normalized_ndvi))  # Ensure within [0,1]
        ndvi_color = mcolors.to_hex(cmap(normalized_ndvi))  # Convert to hex

        return {
            "color": "black",  # Keep a thin black border
            "weight": 0.7,     # Reduce border thickness
            "fillColor": ndvi_color,  # Use the colormap for fill
            "fillOpacity": 0.6,  # Semi-transparent fill
        }

    # Add polygons as GeoJSON (preserving properties)
    folium.GeoJson(
        geojson_data,  # Use the whole GeoJSON object
        style_function=get_style,
        tooltip=folium.GeoJsonTooltip(fields=["LOCALITà", "TESI", "mean_ndvi",  "min_ndvi",  "max_ndvi",  "std_ndvi"], 
                                      aliases=["Località:", "Tesi:", "NDVI Mean:", "NDVI Min:", "NDVI Max:", "NDVI Std:"], 
                                      localize=True,
                                      labels=True,
                                      sticky=True
                                      )
    ).add_to(ndvi_map)

    # Render the map to HTML string
    map_html = ndvi_map._repr_html_()
    return map_html

@router.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    file_path = os.path.join('uploads', file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
    return {"filename": file.filename, "filepath": file_path}

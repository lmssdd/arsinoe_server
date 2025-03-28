from aquacrop import AquaCropModel, Soil, Crop, InitialWaterContent
from aquacrop.utils import prepare_weather, get_filepath

from datetime import datetime, timedelta
import pandas as pd
import glob
import os
import numpy as np
import requests
import matplotlib
matplotlib.use("Agg")  # Imposta un backend non interattivo
import matplotlib.pyplot as plt

aquacrop_fname = "static/files/CMCC_CM2_VHR4.txt"


def aquacrop_run(fname=aquacrop_fname):

  weather_data = prepare_weather(fname)

  #sandy_clay_loam = Soil(soil_type='SandyClayLoam')
  soil_ussana=Soil('custom') # Ussana
  soil_ussana.add_layer_from_texture(thickness=soil_ussana.zSoil,
                                  Sand=56.4,Clay=22.5,
                                  OrgMat=1.2,penetrability=100)
  wheat = Crop('Wheat', planting_date='12/01')

  #wheat.CC0 = 0.3

  InitWC = InitialWaterContent( value=['FC'] )

  # combine into aquacrop model and specify start and end simulation date
  model = AquaCropModel( sim_start_time=f'{1950}/12/01',
                         sim_end_time=f'{2050}/07/30',
                         weather_df=weather_data,
                         soil=soil_ussana,  # sandy_clay_loam,
                         crop=wheat,
                         initial_water_content=InitWC )

  # run model till termination
  model.run_model(till_termination=True)

  return model

def aquacrop_run_benatzu(fname=aquacrop_fname):

  weather_data = prepare_weather(fname)
  
  #sandy_clay_loam = Soil(soil_type='SandyClayLoam')
  soil_benatzu=Soil('custom') # Benatzu
  soil_benatzu.add_layer_from_texture(thickness=soil_benatzu.zSoil,
                                  Sand=26.2,Clay=39.4,
                                  OrgMat=2.8,penetrability=100)
  wheat = Crop('Wheat', planting_date='12/15')

  #wheat.CC0 = 0.3

  InitWC = InitialWaterContent( value=['FC'] )

  # combine into aquacrop model and specify start and end simulation date
  model = AquaCropModel( sim_start_time=f'{1950}/12/15',
                         sim_end_time=f'{2023}/07/30',
                         weather_df=weather_data,
                         soil=soil_benatzu,  # sandy_clay_loam,
                         crop=wheat,
                         initial_water_content=InitWC )

  # run model till termination
  model.run_model(till_termination=True)

  return model

def aquacrop_run_ussana(fname=aquacrop_fname):

  weather_data = prepare_weather(fname)

  #sandy_clay_loam = Soil(soil_type='SandyClayLoam')
  soil_ussana=Soil('custom') # Ussana
  soil_ussana.add_layer_from_texture(thickness=soil_ussana.zSoil,
                                  Sand=56.4,Clay=22.5,
                                  OrgMat=1.2,penetrability=100)
  wheat = Crop('Wheat', planting_date='12/15')

  #wheat.CC0 = 0.3

  InitWC = InitialWaterContent( value=['FC'] )

  # combine into aquacrop model and specify start and end simulation date
  model = AquaCropModel( sim_start_time=f'{1950}/12/15',
                         sim_end_time=f'{2023}/07/30',
                         weather_df=weather_data,
                         soil=soil_ussana,  # sandy_clay_loam,
                         crop=wheat,
                         initial_water_content=InitWC )

  # run model till termination
  model.run_model(till_termination=True)

  return model


def reorganize_gens_json(data):
    hourly_data = data['hourly']
    ensemble_dfs = {}
    time_series = hourly_data['time']

    for i in range(0, 31):
        if(i > 0):
            member_key_temp = f'temperature_2m_member{i:02d}'
            member_key_precip = f'precipitation_member{i:02d}'
            member_key_et0 = f'et0_fao_evapotranspiration_member{i:02d}'
        else:
            member_key_temp = 'temperature_2m'
            member_key_precip = 'precipitation'
            member_key_et0 = 'et0_fao_evapotranspiration'

        if member_key_temp in hourly_data and member_key_precip in hourly_data and member_key_et0 in hourly_data:
            df = pd.DataFrame({
                'time': time_series,
                'temperature_2m': hourly_data[member_key_temp],
                'precipitation': hourly_data[member_key_precip],
                'et0_fao_evapotranspiration': hourly_data[member_key_et0]
            })
            df.index = pd.to_datetime(df.time)
            df.drop('time', axis=1, inplace=True)
            df_daily = pd.DataFrame()
            df_daily['temperature_2m_max'] = df.temperature_2m.resample('D').max()
            df_daily['temperature_2m_min'] = df.temperature_2m.resample('D').min()
            df_daily['precipitation_sum'] = df.precipitation.resample('D').sum()
            df_daily['et0_fao_evapotranspiration'] = df.et0_fao_evapotranspiration.resample('D').sum()
            ensemble_dfs[f'member_{i:02d}'] = df_daily.copy()
        else:
            print(f"Warning: Missing data for member {i:02d}")

    return ensemble_dfs


def plot_wprof_out(models, name, past_days=30, forecast_days=30):
    fig, axs = plt.subplots(4, 3, figsize=(12, 9))
    axs = axs.flatten()

    for i in range(1, 13):
        th_all_members = np.array([
            getattr(models[m]._outputs.water_storage[-forecast_days:], f"th{i}")
            for m in range(31)
        ])
        th_all_members[th_all_members == 0] = np.nan
        q10 = np.percentile(th_all_members, 10, axis=0)
        q25 = np.percentile(th_all_members, 25, axis=0)
        q50 = np.percentile(th_all_members, 50, axis=0)
        q75 = np.percentile(th_all_members, 75, axis=0)
        q90 = np.percentile(th_all_members, 90, axis=0)
        x = np.arange(th_all_members.shape[1])

        axs[i-1].fill_between(x, q10, q90, color='gray', alpha=0.2)
        axs[i-1].fill_between(x, q25, q75, color='blue', alpha=0.3)
        axs[i-1].plot(x, q50, color='black', linewidth=1.5)

        axs[i-1].set_title(f"{name} th{i}")
        axs[i-1].grid(True)
        axs[i-1].tick_params(axis='both', which='major', labelsize=8)
        axs[i-1].set_ylim(0.1, 0.45)
        if i > 9:
            axs[i-1].set_xlabel('Day')
        if i % 3 == 1:
            axs[i-1].set_ylabel('WC')

    plt.tight_layout()
    plt.savefig(f'water_profile_quantiles_{name}.png')
    plt.close()

def get_site_config(site: str):
    site_config = {
        "Ussana": {
            "lat": 39.4104, "lon": 9.0910,
            "sand": 56.4, "clay": 22.5, "orgmat": 1.2,
            "fc_ref": 116, "planting_date": "12/03", "harvest_date": "04/22"
        },
        "Benatzu": {
            "lat": 39.3500, "lon": 8.9600,
            "sand": 26.2, "clay": 39.4, "orgmat": 2.8,
            "fc_ref": 58, "planting_date": "12/15", "harvest_date": "04/30"
        }
    }
    if site not in site_config:
        raise ValueError(f"Sito non supportato: {site}")
    return site_config[site]

def get_weather_data(cfg, site, semina, today_str):
    print(f"[{site}] Recupero dati meteo storici...")
    data_dir = "./data"
    os.makedirs(data_dir, exist_ok=True)
    storico_path = f"{data_dir}/{today_str}_storico.csv"
    pre_semina = semina - timedelta(days=31)
    end_storico = datetime.today()

    if not os.path.exists(storico_path):
        print(f"[{site}] Scarico da Open-Meteo")
        url = (
            f"https://archive-api.open-meteo.com/v1/archive?"
            f"latitude={cfg['lat']}&longitude={cfg['lon']}"
            f"&start_date={pre_semina.strftime('%Y-%m-%d')}"
            f"&end_date={end_storico.strftime('%Y-%m-%d')}"
            "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration"
            "&timezone=Europe%2FRome"
        )
        res = requests.get(url).json()
        df_storico = pd.DataFrame(res["daily"])
        df_storico.index = pd.to_datetime(df_storico.pop("time"))
        df_storico.to_csv(storico_path)
    else:
        print(f"[{site}] Uso dati locali")
        df_storico = pd.read_csv(storico_path, index_col=0, parse_dates=True)

    return df_storico

def get_ensemble_data(cfg, site, today_str, df_storico):
    print(f"[{site}] Recupero dati ensemble...")
    data_dir = "./data"
    ensemble_data = {}
    ensemble_files = sorted(glob.glob(f"{data_dir}/{today_str}_gens_member*.csv"))

    if not ensemble_files:
        print(f"[{site}] Scarico ensemble da Open-Meteo")
        url = (
            f"https://ensemble-api.open-meteo.com/v1/ensemble?"
            f"latitude={cfg['lat']}&longitude={cfg['lon']}"
            "&hourly=temperature_2m,precipitation,et0_fao_evapotranspiration"
            "&past_days=31&forecast_days=30&models=gfs_seamless"
        )
        res = requests.get(url).json()
        gens_dataframes = reorganize_gens_json(res)
        for name, df in gens_dataframes.items():
            df.to_csv(f"{data_dir}/{today_str}_gens_{name}.csv")
    else:
        print(f"[{site}] Uso dati ensemble locali")
        gens_dataframes = {}
        for path in ensemble_files:
            name = path.split("_gens_")[1].replace(".csv", "")
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            gens_dataframes[name] = df

    print(f"[{site}] Debiasing e merge...")
    for i in range(31):
        member = f"member_{i:02d}"
        df_ens = gens_dataframes[member]
        if i == 0:
            common = df_ens.index.intersection(df_storico.index)
            ens_avg = df_ens.loc[common].mean()
            era_avg = df_storico.loc[common].mean()
        df_ens['temperature_2m_max'] += era_avg['temperature_2m_max'] - ens_avg['temperature_2m_max']
        df_ens['temperature_2m_min'] += era_avg['temperature_2m_min'] - ens_avg['temperature_2m_min']
        if ens_avg['precipitation_sum'] > 0:
            df_ens['precipitation_sum'] *= era_avg['precipitation_sum'] / ens_avg['precipitation_sum']
        if ens_avg['et0_fao_evapotranspiration'] > 0:
            df_ens['et0_fao_evapotranspiration'] *= era_avg['et0_fao_evapotranspiration'] / ens_avg['et0_fao_evapotranspiration']
        df_merged = pd.concat([df_storico, df_ens[~df_ens.index.isin(df_storico.index)]])
        ensemble_data[member] = df_merged

    return ensemble_data

def simulate_models(ensemble_data, cfg, semina, site):
    print(f"[{site}] Simulazione modelli AquaCrop...")
    pre_semina = semina - timedelta(days=31)
    df0 = ensemble_data["member_00"]
    p_pre = df0["precipitation_sum"][(df0.index >= pre_semina) & (df0.index < semina)].sum()
    raccolta = df0.index.max()

    soil = Soil("custom")
    soil.add_layer_from_texture(thickness=soil.zSoil, Sand=cfg["sand"], Clay=cfg["clay"], OrgMat=cfg["orgmat"], penetrability=100)
    crop = Crop("Wheat", planting_date=cfg["planting_date"], harvest_date=cfg["harvest_date"], Zmin=0.05)
    InitWC = InitialWaterContent(wc_type="Pct", value=[100 * min(p_pre / cfg["fc_ref"], 1)])

    models = {}
    for m in range(31):
        df = ensemble_data[f"member_{m:02d}"]
        weather = pd.DataFrame({
            "MinTemp": df["temperature_2m_min"],
            "MaxTemp": df["temperature_2m_max"],
            "Precipitation": df["precipitation_sum"],
            "ReferenceET": df["et0_fao_evapotranspiration"],
            "Date": df.index
        }, index=df.index)

        model = AquaCropModel(
            sim_start_time=semina.strftime('%Y/%m/%d'),
            sim_end_time=raccolta.strftime('%Y/%m/%d'),
            weather_df=weather,
            soil=soil,
            crop=crop,
            initial_water_content=InitWC
        )
        model.run_model(till_termination=True)
        models[m] = model

    return models

def run_ensemble_and_generate_plot(site: str, force: bool = False) -> str:
    print(f"\n=== Avvio simulazione per {site} ===")
    today_str = datetime.today().strftime('%Y%m%d')
    output_path = f"static/png/water_profile_quantiles_{site}_{today_str}.png"

    if os.path.exists(output_path) and not force:
        print(f"[{site}] 🟡 Immagine già disponibile: {output_path}")
        return output_path
    elif os.path.exists(output_path) and force:
        print(f"[{site}] 🔁 Forzo rigenerazione dell'immagine per {site}")
    
    semina = pd.to_datetime("2024-12-03")
    cfg = get_site_config(site)

    df_storico = get_weather_data(cfg, site, semina, today_str)
    ensemble_data = get_ensemble_data(cfg, site, today_str, df_storico)
    models = simulate_models(ensemble_data, cfg, semina, site)

    os.makedirs("static/png", exist_ok=True)
    today_str = datetime.today().strftime('%Y%m%d')
    output_path = f"static/png/water_profile_quantiles_{site}_{today_str}.png"
    plot_wprof_out(models, site)
    os.replace(f"water_profile_quantiles_{site}.png", output_path)
    print(f"[{site}] ✅ Immagine salvata: {output_path}\n")
    return output_path

if __name__ == '__main__':
  filename = run_ensemble_and_generate_plot("Ussana")
  print(f"Image saved as: {filename}")
  #model = aquacrop_run(  )
  #print( model._outputs.final_stats )


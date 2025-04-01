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
import traceback


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



def run_ensemble_and_generate_plot(location: str, force: bool = False) -> str:
    data_dir = './data'

    if location == "Ussana":
        lat, lon = 39.41043974519125, 9.09101345584236
    elif location == "Benatzu":
        lat, lon = 39.4259, 8.9575
    else:
        raise ValueError("Unsupported location")
    
    today_str =  datetime.today().strftime('%Y%m%d')
    today = datetime.strptime(today_str, "%Y%m%d")
    data_semina = '20241203'
    data_semina_dt = datetime.strptime(data_semina, "%Y%m%d")
    data_inizio_storico = data_semina_dt - timedelta(days=31)
    data_fine_storico = datetime.today()

    csv_storico=glob.glob(f'{data_dir}/{today_str}_storico.csv')

    if not csv_storico:  # Se i file CSV non esistono, li genera e scarica i dati
        print('Scarico dati storici')
        # Scarica i dati storici
        url_storico = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={data_inizio_storico.strftime('%Y-%m-%d')}&end_date={data_fine_storico.strftime('%Y-%m-%d')}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration&timezone=Europe%2FRome"
        risposta_storico = requests.get(url_storico)
        dati_storico = risposta_storico.json()
        df_storico = pd.DataFrame(dati_storico["daily"])
        df_storico.index = pd.to_datetime(df_storico.time)
        df_storico.drop('time', axis=1, inplace=True)
        df_storico.dropna(inplace=True)
        df_storico.to_csv(f'{data_dir}/{today_str}_storico.csv')
    else:  # Se i file CSV esistono, li carica
        print('Leggo dati storici')
        df_storico=pd.read_csv(f'{data_dir}/{today_str}_storico.csv',index_col=0)
        df_storico.index = pd.to_datetime(df_storico.index)

    # Controllo dell'esistenza dei file CSV
    csv_files = sorted(glob.glob(f'{data_dir}/{today_str}_gens_member*.csv'))

    if not csv_files:  # Se i file CSV non esistono, li genera e scarica i dati
        print('Scarico previsioni gens')
        # Scarica i dati di previsione
        url_previsione = f'https://ensemble-api.open-meteo.com/v1/ensemble?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation,et0_fao_evapotranspiration&past_days=31&forecast_days=30&models=gfs_seamless'
        risposta_previsione = requests.get(url_previsione)
        dati_previsione = risposta_previsione.json()    
        gens_dataframes = reorganize_gens_json(dati_previsione)
        for name, df in gens_dataframes.items():
            df.to_csv(f'{data_dir}/{today_str}_gens_{name}.csv')
    else:  # Se i file CSV esistono, li carica
        print('Leggo previsioni gens')
        gens_dataframes = {}
        member_list = [file_path.replace(f'{data_dir}/{today_str}_gens_', '').replace('.csv', '') for file_path in csv_files]
        for m, filename in enumerate(csv_files):
            name = f'{member_list[m]}'
            df = pd.read_csv(filename, index_col=0)
            df.index = pd.to_datetime(df.index)
            df['Date'] = df.index
            gens_dataframes[name] = df
    
    # merge storico e previsioni
    debias=True
    ensemble_dataframes = {}
    # Crea DataFrame per ogni membro dell'ensemble
    for m in range(0, 31):
        member_name=f'member_{m:02d}'
                    # Stampa i valori medi per 'member_00' se sovrapposti
        df_daily=gens_dataframes[member_name]
        if m == 0:
            overlapping_dates=df_daily.index.intersection(df_storico.index)
            df1_comune = df_daily.loc[overlapping_dates]
            df2_comune = df_storico.loc[overlapping_dates]
            ENS_av=df1_comune.mean()
            ERA5_av=df2_comune.mean()
            print(ENS_av)
            print(ERA5_av)
        if(debias):
            df_daily['temperature_2m_max'] += ERA5_av['temperature_2m_max']-ENS_av['temperature_2m_max']
            df_daily['temperature_2m_min'] += ERA5_av['temperature_2m_min']-ENS_av['temperature_2m_min']
            if(ENS_av['precipitation_sum']>0):
                df_daily['precipitation_sum'] *= ERA5_av['precipitation_sum']/ENS_av['precipitation_sum']
            if(ENS_av['et0_fao_evapotranspiration']>0):
                df_daily['et0_fao_evapotranspiration'] *= ERA5_av['et0_fao_evapotranspiration']/ENS_av['et0_fao_evapotranspiration']
        # Rimuovi le righe sovrapposte da df2
        df_daily = df_daily[~df_daily.index.isin(df_storico.index)]
        # Concatena i DataFrame
        ensemble_dataframes[f'member_{m:02d}'] = pd.concat([df_storico,df_daily])
    for name, df in ensemble_dataframes.items():
        df.to_csv(f'{data_dir}/{today_str}_{name}.csv')

    # runna aquacrop
    weather_data=ensemble_dataframes['member_00']
    semina='2024-12-03'
    semina=pd.to_datetime(semina)#-timedelta(pre_days)
    pre_semina=pd.to_datetime(semina)-timedelta(30)
    giorni_pre_semina=(weather_data.index>=pre_semina)&(weather_data.index<semina)
    p_pre=weather_data['precipitation_sum'][giorni_pre_semina].sum()
    giorni_semina=(weather_data.index>semina).sum()
    raccolta=semina+timedelta(len(weather_data)-32)#weather_data.index[-7]

    today_index=((weather_data.index>semina)&(weather_data.index<today)).sum()

    empirical=True
    day=semina.day
    durata=giorni_semina

    # Inizializza il modello della coltura
    local_wheat = Crop('Wheat',
        planting_date='12/03',
        harvest_date='04/22',
                    Zmin=0.05)

    z=np.linspace(0.05,1.15,12)

    if location == "Ussana":
        soil = Soil('custom')#,dz=[0.1]*20) # Ussana
        soil.add_layer_from_texture(thickness=soil.zSoil, 
                                    Sand=56.4,Clay=22.5,OrgMat=1.2,penetrability=100)
        InitWC = InitialWaterContent(wc_type='Pct',value=[100*min(p_pre/116,1)])
    elif location == "Benatzu":
        soil = Soil('custom')#,dz=[0.1]*20) # Benatzu
        soil.add_layer_from_texture(thickness=soil.zSoil, 
                                    Sand=26.2,Clay=39.4,OrgMat=2.8,penetrability=100)
        InitWC = InitialWaterContent(wc_type='Pct',value=[100*min(p_pre/58,1)])
    else:
        raise ValueError("Unsupported location")
    
    models={}
    for m in range(31):
        # define ussana_weather_data
        weather_data=pd.DataFrame()
        weather_data.index=ensemble_dataframes[f'member_{m:02d}'].index
        weather_data['MinTemp']=ensemble_dataframes[f'member_{m:02d}'].temperature_2m_min
        weather_data['MaxTemp']=ensemble_dataframes[f'member_{m:02d}'].temperature_2m_max
        weather_data['Precipitation']=ensemble_dataframes[f'member_{m:02d}'].precipitation_sum
        weather_data['ReferenceET']=ensemble_dataframes[f'member_{m:02d}'].et0_fao_evapotranspiration
        weather_data['Date']=weather_data.index
        #print(m,weather_data.mean())
        mu = AquaCropModel(sim_start_time=datetime.strftime(semina, '%Y/%m/%d'),
                    sim_end_time=datetime.strftime(raccolta, '%Y/%m/%d'),
                    weather_df=weather_data,
                    soil=soil,
                    crop=local_wheat,
                    initial_water_content=InitWC)
        mu.run_model(till_termination=True)  
        models[m]=mu

    output_path = os.path.join("static/png", f"water_profile_quantiles_{location}_{today_str}.png")
    if os.path.exists(output_path) and not force:
        return output_path
    
    plot_wprof_out(models, location, output_path)

    return output_path


def reorganize_gens_json(data):
    """
    Riorganizza il JSON in un dizionario di 30 DataFrame, uno per membro dell'ensemble.

    Args:
        data (dict): Il JSON fornito.

    Returns:
        dict: Un dizionario di DataFrame, dove le chiavi sono i nomi dei membri dell'ensemble.
    """

    hourly_data = data['hourly']
    ensemble_dfs = {}

    # Estrai i tempi comuni
    time_series = hourly_data['time']

    # Crea DataFrame per ogni membro dell'ensemble
    for i in range(0, 31):
        if(i>0):
            member_key_temp = f'temperature_2m_member{i:02d}'
            member_key_precip = f'precipitation_member{i:02d}'
            member_key_et0 = f'et0_fao_evapotranspiration_member{i:02d}'
        else: #control forecast
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
            df.index=pd.to_datetime(df.time)
            df.drop('time',axis=1,inplace=True)
            df_daily=pd.DataFrame()
            df_daily['temperature_2m_max']=df.temperature_2m.resample('D').max()
            df_daily['temperature_2m_min']=df.temperature_2m.resample('D').min()
            df_daily['precipitation_sum']=df.precipitation.resample('D').sum()
            df_daily['et0_fao_evapotranspiration']=df.et0_fao_evapotranspiration.resample('D').sum()
                        
            ensemble_dfs[f'member_{i:02d}'] = df_daily.copy()
        else:
            print(f"Warning: Missing data for member {i:02d}")

    return ensemble_dfs


def plot_wprof_out(models, name, save_path, forecast_days=30):
    fig, axs = plt.subplots(4, 3, figsize=(12, 9))
    axs = axs.flatten()
    for i in range(1, 13):
        th_all = np.array([getattr(models[m]._outputs.water_storage[-forecast_days:], f"th{i}") for m in range(31)])
        th_all[th_all == 0] = np.nan
        q10, q25, q50, q75, q90 = np.percentile(th_all, [10, 25, 50, 75, 90], axis=0)
        x = np.arange(th_all.shape[1])
        axs[i - 1].fill_between(x, q10, q90, color='gray', alpha=0.2)
        axs[i - 1].fill_between(x, q25, q75, color='blue', alpha=0.3)
        axs[i - 1].plot(x, q50, color='black', linewidth=1.5)
        axs[i - 1].set_title(f"{name} th{i}")
        axs[i - 1].grid(True)
        axs[i - 1].tick_params(labelsize=8)
        axs[i - 1].set_ylim(0.1, 0.45)
        if i > 9: axs[i - 1].set_xlabel('Day')
        if i % 3 == 1: axs[i - 1].set_ylabel('WC')
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()

if __name__ == '__main__':
  filename = run_ensemble_and_generate_plot("Ussana")
  print(f"Image saved as: {filename}")
  #model = aquacrop_run(  )
  #print( model._outputs.final_stats )


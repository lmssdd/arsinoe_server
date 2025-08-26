from aquacrop import AquaCropModel, Soil, Crop, InitialWaterContent, IrrigationManagement
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
  year_start = weather_data.index.year.min()
  year_stop = weather_data.index.year.max()

  #sandy_clay_loam = Soil(soil_type='SandyClayLoam')
  soil_ussana=Soil('custom') # Ussana
  soil_ussana.add_layer_from_texture(thickness=soil_ussana.zSoil,
                                  Sand=56.4,Clay=22.5,
                                  OrgMat=1.2,penetrability=100)
  wheat = Crop('Wheat', planting_date='12/01')

  #wheat.CC0 = 0.3

  InitWC = InitialWaterContent( value=['FC'] )

  # combine into aquacrop model and specify start and end simulation date
  model = AquaCropModel( sim_start_time=f'{year_start}/12/01',
                         sim_end_time=f'{year_stop}/07/30',
                         weather_df=weather_data,
                         soil=soil_ussana,  # sandy_clay_loam,
                         crop=wheat,
                         initial_water_content=InitWC )

  # run model till termination
  model.run_model(till_termination=True)

  return model

def aquacrop_run_benatzu(fname=aquacrop_fname, irr: int=0):

  weather_data = prepare_weather(fname)
  year_start = weather_data.index.year.min()
  year_stop = weather_data.index.year.max()
  
  #sandy_clay_loam = Soil(soil_type='SandyClayLoam')
  soil_benatzu=Soil('custom') # Benatzu
  soil_benatzu.add_layer_from_texture(thickness=soil_benatzu.zSoil,
                                  Sand=26.2,Clay=39.4,
                                  OrgMat=2.8,penetrability=100)
  wheat = Crop('Wheat', planting_date='12/15')

  #wheat.CC0 = 0.3
  

  InitWC = InitialWaterContent( value=['FC'] )
  irr_mngt = IrrigationManagement(irrigation_method=1,SMT=[irr]*4) # specify irrigation management
    
  if irr == 0:
    # combine into aquacrop model and specify start and end simulation date
    model = AquaCropModel(sim_start_time=f'{year_start}/12/15',
                          sim_end_time=f'{year_stop}/07/30',
                          weather_df=weather_data,
                          soil=soil_benatzu,  # sandy_clay_loam,
                          crop=wheat,
                          initial_water_content=InitWC)
  else:
    # combine into aquacrop model and specify start and end simulation date
    model = AquaCropModel(sim_start_time=f'{year_start}/12/15',
                          sim_end_time=f'{year_stop}/07/30',
                          weather_df=weather_data,
                          soil=soil_benatzu,  # sandy_clay_loam,
                          crop=wheat,
                          initial_water_content=InitWC,
                          irrigation_management=irr_mngt)

  # run model till termination
  model.run_model(till_termination=True)

  return model

def aquacrop_run_ussana(fname=aquacrop_fname, irr: int=0):

  weather_data = prepare_weather(fname)
  year_start = weather_data.index.year.min()
  year_stop = weather_data.index.year.max()

  #sandy_clay_loam = Soil(soil_type='SandyClayLoam')
  soil_ussana=Soil('custom') # Ussana
  soil_ussana.add_layer_from_texture(thickness=soil_ussana.zSoil,
                                  Sand=56.4,Clay=22.5,
                                  OrgMat=1.2,penetrability=100)
  wheat = Crop('Wheat', planting_date='12/15')

  #wheat.CC0 = 0.3

  InitWC = InitialWaterContent( value=['FC'] )
  irr_mngt = IrrigationManagement(irrigation_method=1,SMT=[irr]*4) # specify irrigation management
  
  if irr == 0:
    # combine into aquacrop model and specify start and end simulation date
    model = AquaCropModel(sim_start_time=f'{year_start}/12/15',
                          sim_end_time=f'{year_stop}/07/30',
                          weather_df=weather_data,
                          soil=soil_ussana,  # sandy_clay_loam,
                          crop=wheat,
                          initial_water_content=InitWC)
  else:
    # combine into aquacrop model and specify start and end simulation date
    model = AquaCropModel(sim_start_time=f'{year_start}/12/15',
                          sim_end_time=f'{year_stop}/07/30',
                          weather_df=weather_data,
                          soil=soil_ussana,  # sandy_clay_loam,
                          crop=wheat,
                          initial_water_content=InitWC,
                          irrigation_management=irr_mngt)

  # run model till termination
  model.run_model(till_termination=True)

  return model



def run_ensemble_and_generate_plot(location: str, force: bool = False, irr: int=0) -> tuple[str, str]:
    data_dir = 'static/data'

    data_semina = '20241203'

    if location == "Ussana":
        lat, lon = 39.41043974519125, 9.09101345584236 
    elif location == "Benatzu":
        lat, lon = 39.4259, 8.9575
    else:
        raise ValueError("Unsupported location")
    
    today_str =  datetime.today().strftime('%Y%m%d')
    today = datetime.strptime(today_str, "%Y%m%d")
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
            #print(ENS_av)
            #print(ERA5_av)
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
    semina=data_semina
    semina=pd.to_datetime(semina)#-timedelta(pre_days)
    pre_semina=pd.to_datetime(semina)-timedelta(30)
    giorni_pre_semina=(weather_data.index>=pre_semina)&(weather_data.index<semina)
    p_pre=weather_data['precipitation_sum'][giorni_pre_semina].sum()
    giorni_semina=(weather_data.index>semina).sum()
    raccolta=weather_data.index[-1]

    today_index=((weather_data.index>semina)&(weather_data.index<today)).sum()

    empirical=True
    day=semina.day
    durata=giorni_semina

    date_object = datetime.strptime(data_semina, '%Y%m%d')
    formatted_date = date_object.strftime('%m/%d')

    # Inizializza il modello della coltura
    local_wheat = Crop('Wheat',
        planting_date=formatted_date,
        harvest_date=raccolta.strftime('%m/%d'),
                    Zmin=0.05,Zmax=0.45)

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

    irr_mngt = IrrigationManagement(irrigation_method=1,SMT=[irr]*4) # specify irrigation management

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
        if irr==0:
            mu = AquaCropModel(sim_start_time=datetime.strftime(semina, '%Y/%m/%d'),
                        sim_end_time=datetime.strftime(raccolta, '%Y/%m/%d'),
                        weather_df=weather_data,
                        soil=soil,
                        crop=local_wheat,
                        initial_water_content=InitWC)
        else:
            mu = AquaCropModel(sim_start_time=datetime.strftime(semina, '%Y/%m/%d'),
                        sim_end_time=datetime.strftime(raccolta, '%Y/%m/%d'),
                        weather_df=weather_data,
                        soil=soil,
                        crop=local_wheat,
                        initial_water_content=InitWC,
                        irrigation_management=irr_mngt)
        mu.run_model(till_termination=True)  
        models[m]=mu

    water_path = os.path.join("static/png", f"water_profile_quantiles_{location}_{today_str}.png")
    outputs_path = os.path.join("static/png", f"model_outputs_{location}_{today_str}.png")
    #if os.path.exists(water_path) and os.path.exists(outputs_path) and not force:
    #    return water_path, outputs_path
    
    plot_wprof_out(models, location, water_path)
    plot_ensemble_quantiles(models, name, outputs_path)

    return water_path, outputs_path


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
    #print('PLOT__________________', forecast_days)
    fig, axs = plt.subplots(2, 3, figsize=(12, 4.5))
    axs = axs.flatten()
    for i in range(1, 7):
        #th_all = np.array([getattr(models[m]._outputs.water_storage[-forecast_days:-forecast_days+15], f"th{i}") for m in range(31)])
        th_all = np.array([getattr(models[m]._outputs.water_storage[-30:], f"th{i}") for m in range(31)])
        th_all[th_all == 0] = np.nan
        #print(th_all.shape)
        #print(th_all)
        q10, q25, q50, q75, q90 = np.percentile(th_all, [10, 25, 50, 75, 90], axis=0)
        x = np.arange(th_all.shape[1])
        axs[i - 1].fill_between(x, q10, q90, color='gray', alpha=0.2)
        axs[i - 1].fill_between(x, q25, q75, color='blue', alpha=0.3)
        axs[i - 1].plot(x, q50, color='black', linewidth=1.5)
        axs[i - 1].set_title(f"{name} th{i}")
        axs[i - 1].grid(True)
        axs[i - 1].tick_params(labelsize=8)
        #axs[i - 1].set_ylim(0.1, 0.45)
        if i > 3: axs[i - 1].set_xlabel('Day')
        if i % 3 == 1: axs[i - 1].set_ylabel('WC')
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()

def plot_ensemble_quantiles(models, name, save_path, drop_days=0):
    """
    Generates a figure with 16 subplots, showing the median and quantile areas
    (10, 25, 75, 90 percentiles) for various model output variables.

    Args:
        models (list): A list of model objects, each with a '_outputs' attribute
                    containing the time series data.
        name (str): A string to be used in the titles and labels of the plots.
        drop_days (int, optional): The number of last days to exclude from
                                    the time series. Defaults to 30.
    """
    fig, axs = plt.subplots(4, 4, figsize=(12, 9))
    axs = axs.flatten()
    n_members = len(models)

    # Prepare a dictionary to hold all ensemble time series for each variable
    ensemble_data = {
        'gdd': [],
        'gdd_cum': [],
        'z_root': [],
        'canopy_cover': [],
        'canopy_cover_ns': [],
        'biomass': [],
        'biomass_ns': [],
        'harvest_index': [],
        'harvest_index_adj': [],
        'yield_': [],
        'Wr': [],
        'Infl': [],
        'Runoff': [],
        'DeepPerc': [],
        'Es': [],
        'EsPot': [],
        'Tr': [],
        'TrPot': [],
        'th1': [],
        'Infl_cum': [],
        'Es_cum': []
    }

    # Extract data for all ensemble members
    for m in range(n_members):
        outputs = models[m]._outputs.crop_growth
        fluxes = models[m]._outputs.water_flux
        storage = models[m]._outputs.water_storage
        last_day=(outputs.gdd_cum[:]!=0).sum()
        #print(outputs.columns)
        ensemble_data['gdd'].append(outputs.gdd[-drop_days:last_day])
        ensemble_data['gdd_cum'].append(outputs.gdd_cum[-drop_days:last_day])
        ensemble_data['z_root'].append(outputs.z_root[:last_day])
        ensemble_data['canopy_cover'].append(outputs.canopy_cover_ns[-drop_days:last_day]-outputs.canopy_cover[-drop_days:last_day])
        #ensemble_data['canopy_cover'].append(outputs.canopy_cover[-drop_days:-1])
        #ensemble_data['canopy_cover_ns'].append(outputs.canopy_cover_ns[-drop_days:-1])
        ensemble_data['biomass'].append(outputs.biomass_ns[-drop_days:last_day]-outputs.biomass[-drop_days:last_day])
        #ensemble_data['biomass'].append(outputs.biomass[-drop_days:-1])
        #ensemble_data['biomass_ns'].append(outputs.biomass_ns[-drop_days:-1])
        ensemble_data['harvest_index'].append(outputs.harvest_index_adj[-drop_days:last_day]-outputs.harvest_index[-drop_days:last_day])
        #ensemble_data['harvest_index'].append(outputs.harvest_index[-drop_days:-1])
        #ensemble_data['harvest_index_adj'].append(outputs.harvest_index_adj[-drop_days:-1])
        
        #ensemble_data['yield_'].append(outputs.yield_[-drop_days:-1])
        
        ensemble_data['yield_'].append(outputs.DryYield[-drop_days:last_day])
        ensemble_data['Wr'].append(fluxes.Wr[-drop_days:last_day])
        ensemble_data['Infl'].append(fluxes.Infl[-drop_days:last_day])
        ensemble_data['Runoff'].append(fluxes.Runoff[-drop_days:last_day])
        #ensemble_data['DeepPerc'].append(fluxes.DeepPerc[-drop_days:-1])
        ensemble_data['Es'].append(fluxes.Es[-drop_days:last_day])
        ensemble_data['EsPot'].append(fluxes.EsPot[-drop_days:last_day])
        ensemble_data['Tr'].append(fluxes.Tr[-drop_days:last_day])
        ensemble_data['TrPot'].append(fluxes.TrPot[-drop_days:last_day])
        ensemble_data['th1'].append(storage.th1[-drop_days:last_day])
        ensemble_data['Infl_cum'].append(fluxes.Infl.cumsum()[:last_day])
        ensemble_data['Es_cum'].append(fluxes.Es.cumsum()[:last_day])
        if(m==0):
            axs[15].plot(models[m]._outputs.water_flux.Infl.cumsum()[:last_day],c='b',label='Pcum')
            axs[15].plot(models[m]._outputs.water_flux.Es.cumsum()[:last_day],c='g',label='Ecum')
            axs[15].grid(True)
        else:
            axs[15].plot(models[m]._outputs.water_flux.Infl.cumsum()[:last_day],c='b')
            axs[15].plot(models[m]._outputs.water_flux.Es.cumsum()[:last_day],c='g')
        max_plu=200
        if m==0:
            axs[15].plot((13,13),(0,max_plu),label='Emergence')
            axs[15].plot((93,93),(0,max_plu),label='MaxRooting')
            axs[15].plot((127,127),(0,max_plu),label='HIstart')
            axs[15].plot((127+15,127+15),(50,max_plu-50),label='Flowering')
            axs[15].plot((158,158),(0,max_plu),label='Senescence')
            axs[15].plot((197,197),(0,max_plu),label='Maturity')
            #axs[15].legend(loc='center left', bbox_to_anchor=(1.5, 1.5),fontsize=8)

        #if(m==0) :
        #    for ax in axs:
        #        ax.grid(True)
        #        ax.legend(fontsize=8)
        #        ax.tick_params(axis='both', which='major', labelsize=8)
        #    axs[15].legend(loc='center left', bbox_to_anchor=(1.5, 1.5),fontsize=8)
        
    # Calculate and plot quantiles for each variable
    variables_to_plot = [
        ('gdd', axs[0], 'GDD'),
        ('gdd_cum', axs[1], 'GDD_CUM'),
        ('z_root', axs[2], 'Z_ROOT'),
        ('canopy_cover', axs[3], 'CC'),
        #('canopy_cover_ns', axs[3], 'CC_ns'),
        ('biomass', axs[4], 'biomass'),
        #('biomass_ns', axs[4], 'biomass_ns'),
        ('harvest_index', axs[5], 'HI'),
        #('harvest_index_adj', axs[5], 'HI_adj'),
        ('yield_', axs[6], 'yield'),
        ('Wr', axs[7], 'Wr'),
        ('Infl', axs[8], 'Infl'),
        ('Runoff', axs[9], 'Runoff'),
        ('DeepPerc', axs[10], 'DeepPerc'),
        ('Es', axs[10], 'Es'),
        ('EsPot', axs[11], 'EsPot'),
        ('Tr', axs[12], 'Tr'),
        ('TrPot', axs[13], 'TrPot'),
        ('th1', axs[14], 'th1'),
        #('Infl_cum', axs[15], 'Pcum', {'color': 'b'}),
        #('Es_cum', axs[15], 'Ecum', {'color': 'g'})
    ]

    for var_name, ax, label, *args in variables_to_plot:
        data = np.array(ensemble_data[var_name])
        if data.size > 0:
            quantiles = np.nanpercentile(data, [10, 25, 50, 75, 90], axis=0)
            x = np.arange(data.shape[1])

            ax.fill_between(x, quantiles[0], quantiles[4], color='gray', alpha=0.2, label=f'{label} 10-90%')
            ax.fill_between(x, quantiles[1], quantiles[3], color='blue', alpha=0.3, label=f'{label} 25-75%')
            ax.plot(x, quantiles[2], color='black', linewidth=1.5, label=f'{label} Median', **(args[0] if args else {}))
            ax.set_title(label)
            ax.grid(True)
            ax.tick_params(axis='both', which='major', labelsize=8)


    # Add legends to other subplots (only once per subplot)
    for ax in axs:
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(handles, labels, fontsize=8)
    axs[15].legend(loc='center left', bbox_to_anchor=(1.0, 0.5),fontsize=8)

    #plt.subplots_adjust(right=0.82)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()


if __name__ == '__main__':
  filename = run_ensemble_and_generate_plot("Ussana")
  print(f"Image saved as: {filename}")
  #model = aquacrop_run(  )
  #print( model._outputs.final_stats )


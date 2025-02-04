from aquacrop import AquaCropModel, Soil, Crop, InitialWaterContent
from aquacrop.utils import prepare_weather, get_filepath

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

if __name__ == "__main__":

  model = aquacrop_run(  )
  print( model._outputs.final_stats )


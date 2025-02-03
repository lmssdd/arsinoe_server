import pandas as pd
import glob, datetime, csv, json

dpcn_path = 'static/mistral_dpcn'
ndvi_path = 'static/fields_ndvi/Ussana'

def precipitation(in_path=dpcn_path, precip_var='B13011' ):
    prec = []
    dates = []
    invalids = 0

    for fname in glob.glob( in_path + '/*.json' ):
      print( 'processing [%s]' % fname )

      with open( fname, mode='r' ) as myf:
        lines = myf.readlines()
        for line in lines:
          obj = json.loads(line)
          staz = obj['data'][0]['vars']['B01019']['v']
          y = obj['data'][0]['vars']['B04001']['v']
          m = obj['data'][0]['vars']['B04002']['v']
          d = obj['data'][0]['vars']['B04003']['v']
          h = obj['data'][0]['vars']['B04004']['v']
          mm = obj['data'][0]['vars']['B04005']['v']
          s = obj['data'][0]['vars']['B04006']['v']

          node = obj['data'][1]['vars']

          tmp = None

          if precip_var in node:
            tmp = node[precip_var]['v']

          date = datetime.datetime(year=y, month=m, day=d, hour=h, minute=mm, second=s)

          if (tmp is None) or (tmp < 0.):
            invalids += 1
            continue

          dates.append( date )
          prec.append( tmp )

    print( 'Invalids count: %d' % invalids )

    df = pd.DataFrame( prec, columns=["Prec"], index=dates )
    df.index.name='Datetime'
    df_day = df["Prec"].resample('D').sum()

    return df_day



def ndvi(in_path=ndvi_path, init_date=None ):

    if init_date is None:
      init_date = datetime.datetime( year=2022, month=11, day=1 )

    DATES = []
    DATA = []
    for idx in range(24): DATA.append( [] )

    for fname in sorted( glob.glob( in_path + '/*/*.csv' ) ):
      print( 'processing [%s]' % fname )

      pos = fname.rfind('/')
      mydate = fname[pos+1:-4]
      yy = int( mydate[0:4] )
      mm = int( mydate[4:6] )
      dd = int( mydate[6:8] )

      if ( yy < 2022 ): continue

      date = datetime.datetime( year=yy, month=mm, day=dd, hour=0, minute=0, second=0 )

      if date < init_date: continue

      DATES.append( date )

      with open( fname, newline='') as csvfile:
        reader = csv.reader( csvfile, delimiter=',', quotechar='|' )
        for row in reader:
          field_id = int( row[0] )
          ndvi     = float( row[1] )
          DATA[ field_id ].append( ndvi )

    df = pd.DataFrame()

    df.index = DATES
    df.index.name = 'Datetime'

    for idx in range(24):
      df[ 'field_' + str(idx) ] = DATA[ idx ]

    return df

def get_total_dataframe():
    df_prec = precipitation()
    df_ndvi = ndvi()  # richiede self.df_day esistente

    df_tot  = pd.concat( [df_prec, df_ndvi], axis=1 )
    df_tot['day'] = df_tot.index

    return df_tot

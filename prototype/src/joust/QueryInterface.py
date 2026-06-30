from astropy.coordinates import SkyCoord
import astropy.units as u
from astropy.table import Table

class QueryInterface():
    
    def __init__(self):
        
        self.obs_id1 = ''
        self.obs_id2 = ''
        self.calib_level = 2
        self.s_region = None
        
        self.download_dir = ''
        
        return
    
    def query_obs(self,obs_id):
        obs = Observations.query_criteria(obs_id=obs_id)
        
        if len(obs)==0:
            self.logging('Could not download observation {}'.format(self.obs_id1))
            return
        
        else:
            return obs
        
    def query_generic(self,inst, pid, targ, filt, t_start, t_min, t_max):
        obs = Observations.query_region(obs_id=obs_id)
        
        if len(obs)==0:
            self.logging('Could not download observation {}'.format(self.obs_id1))
            return
        
        else:
            return obs
        
    def query_coord(self,ra,dec):
        
        c = SkyCoord(ra=ra,dec=dec,unit=u.degree)
        
        obs = Observations.query_region(coordinates=c,radius=5*u.arcmin)
        
        if len(obs)==0:
            self.logging('Could not download observation {}'.format(self.obs_id1))
            return
        
        else:
            return obs
        
    def filter_obs(self,obs, filt, t_start, t_min=30, t_max=365,
                   telescope='JWST',instrument='NIRCAM/IMAGE'):
        
        df = obs.to_pandas()
        
        df = df[df['obs_collection'] == telescope]
        df = df[df['instrument_name'] == instrument]
        df = df[df['filters'] == filt]
        df = df[df['t_obs_release'] > (t_start-t_max)]
        df = df[df['t_obs_release'] < (t_start-t_min)]
                
        obs = Table.from_pandas(df)
                
        return obs
        
    def download_obs(self,obs):
        
        if self.calib_level == 2:
            pSGD = 'CAL'
        else:
            pSGD = 'I2D'
            
        data_products = Observations.get_product_list(obs)
        
        data_products = data_products[data_products['calib_level']==self.calib_level]
        data_products = data_products[data_products['productSubGroupDescription']==pSGD]
                
        Observations.download_products(data_products_by_obs,
                                       extension='fits',
                                       download_dir=self.download_dir)
        
        return
                                      
    def run(self):
                                      
        for obs_id in [self.obs_id1, self.obs_id2]:
            obs = self.query_obs(obs_id)
            self.download_obs(obs)
        
        return
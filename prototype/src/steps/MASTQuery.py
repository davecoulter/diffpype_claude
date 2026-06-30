from astroquery.mast import Observations

class MASTQuery:
    """docstring for MASTQuery"""
    def __init__(self, args):
        
        self.args = args
        
        return

    def query_criteria(self, args):
        

        # coordinates=f'{ra} {dec}',
        # radius=f"{rad} deg",
        # instrument_name=['NIRCAM','NIRCAM/IMAGE'],
        # proposal_id = ['1180'],
        # calib_level=["3"],

        obs_table = Observations.query_criteria(args)


        product_list = Observations.get_unique_product_list(obs_table)


        products = Observations.filter_products(product_list, productSubGroupDescription=["CAL"], extension="fits")




        return




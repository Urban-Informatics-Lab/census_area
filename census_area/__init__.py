import json
import sys
import logging

from census import Census
import esridump
import shapely.geometry
import shapely.geos

try:  # Python 2.7+
    from logging import NullHandler
except ImportError:
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass

logging.getLogger(__name__).addHandler(NullHandler())

BLOCK_GROUP_URL = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2014/MapServer/10'

BLOCK_2010_URL = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Current/MapServer/12'

INCORPORATED_PLACES_TIGER = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Current/MapServer/28'

TRACT_URL = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Current/MapServer/8'

class Census(Census):
    def geo_tract(self, fields, geojson_geometry, return_geometry=False):
        filtered_tracts = AreaFilter(geojson_geometry, TRACT_URL)

        features = []
        for tract in filtered_tracts:
            context = {'state' : tract['properties']['STATE'],
                       'county' : tract['properties']['COUNTY']}
            within = 'state:{state} county:{county}'.format(**context)

            tract_id = tract['properties']['TRACT']
            result = self.acs5.get(fields,
                                   {'for': 'tract:{}'.format(tract_id),
                                    'in' :  within})

            if result:
                result, = result
                if return_geometry:
                    tract['properties'].update(result)
                    features.append(tract)
                else:
                    features.append(result)

        if return_geometry:
            return {'type': "FeatureCollection", 'features': features}
        else:
            return features

    def geo_blockgroup(self, fields, geojson_geometry, return_geometry=False):
        filtered_block_groups = AreaFilter(geojson_geometry, BLOCK_GROUP_URL)

        features = []
        for i, block_group in enumerate(filtered_block_groups):
            context = {'state' : block_group['properties']['STATE'],
                       'county' : block_group['properties']['COUNTY'],
                       'tract' : block_group['properties']['TRACT']}
            within = 'state:{state} county:{county} tract:{tract}'.format(**context)

            block_group_id = block_group['properties']['BLKGRP']
            
            result = self.acs5.get(fields,
                                   {'for': 'block group:{}'.format(block_group_id),
                                    'in' :  within})

            if result:
                result, = result
                if return_geometry:
                    block_group['properties'].update(result)
                    features.append(block_group)
                else:
                    features.append(result)

            if i % 100 == 0:
                logging.info('{} block groups'.format(i))
                    

        if return_geometry:
            return {'type': "FeatureCollection", 'features': features}
        else:
            return features

    def geo_block(self, fields, geojson_geometry, return_geometry=False):
        filtered_blocks = AreaFilter(geojson_geometry, BLOCK_2010_URL)

        features = []
        for i, block in enumerate(filtered_blocks):
            context = {'state' : block['properties']['STATE'],
                       'county' : block['properties']['COUNTY'],
                       'tract' : block['properties']['TRACT']}
            within = 'state:{state} county:{county} tract:{tract}'.format(**context)

            block_id = block['properties']['BLOCK']
            result = self.sf1.get(fields,
                                  {'for': 'block:{}'.format(block_id),
                                   'in' :  within})

            if result:
                result, = result
                if return_geometry:
                    block['properties'].update(result)
                    features.append(block)
                else:
                    features.append(result)

            if i % 100 == 0:
                logging.info('{} blocks'.format(i))

        if return_geometry:
            return {'type': "FeatureCollection", 'features': features}
        else:
            return features

    def _state_place_area(self, method, fields, state, place, return_geometry=False):
        search_query = "NAME='{}' AND STATE={}".format(place, state)
        place_dumper = esridump.EsriDumper(INCORPORATED_PLACES_TIGER,
                                           extra_query_args = {'where' : search_query})

        place = next(iter(place_dumper))
        logging.info(place['properties']['NAME'])
        place_geojson = place['geometry']

        return method(fields, place_geojson, return_geometry)

    def state_place_tract(self, *args, **kwargs):
        return self._state_place_area(self.geo_tract, *args, **kwargs)

    def state_place_blockgroup(self, *args, **kwargs):
        return self._state_place_area(self.geo_blockgroup, *args, **kwargs)

    def state_place_block(self, *args, **kwargs):
        return self._state_place_area(self.geo_block, *args, **kwargs)




class AreaFilter(object):
    def __init__(self, geojson_geometry, sub_geography_url):
        self.geo = shapely.geometry.shape(geojson_geometry)

        geo_query_args = {'geometry': ','.join(str(x) for x in self.geo.bounds),
                          'geometryType': 'esriGeometryEnvelope',
                          'spatialRel': 'esriSpatialRelEnvelopeIntersects',
                          'inSR' : '4326',
                          'geometryPrecision' : 9,
                          'orderByFields': 'OID'}
        self.area_dumper = esridump.EsriDumper(sub_geography_url,
                                               extra_query_args = geo_query_args)

    def __iter__(self):
        for area in self.area_dumper:
            area_geo = shapely.geometry.shape(area['geometry'])
            if self.geo.intersects(area_geo):
                try:
                    intersection = self.geo.intersection(area_geo)
                except shapely.geos.TopologicalError:
                    intersection = self.geo.buffer(0).intersection(area_geo.buffer(0))
                if intersection.area/area_geo.area > 0.1:
                    yield area

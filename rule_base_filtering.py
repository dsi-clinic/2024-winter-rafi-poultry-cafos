import geopandas as gpd
import pandas as pd
import ee
import argparse as ap
from geopandas.tools import sjoin
import os

service_account = "earth-engine-rafi@rafi-usa.iam.gserviceaccount.com"
credentials = ee.ServiceAccountCredentials(service_account, "private-key.json")
ee.Initialize(credentials)

parser = ap.ArgumentParser()
parser.add_argument('path', help='Path to the file')
parser.add_argument('-ee', '--ee', action='store_true', default=False, help='Whether to apply exclusion based on land cover')
parser.add_argument('-bd', '--buffer_distance', type=float, default=0, help='Buffer distance value')

args = parser.parse_args()



def filter_by_postprocess_rule(df):
    """
    Filter the dataframe by the postprocess rule

    Input:
        df: a dataframe with all the information from the geojson file

    Output:
        filtered_df: a dataframe that has been filtered by the postprocess rule
    """

    filtered_df = df.loc[
            (df.loc[:,'rectangle_aspect_ratio'].between(3.4, 20.49)) &
            (df.loc[:,'distance_to_nearest_road'] >5) &  # DOUBT: unit of measure?
            (df.loc[:,'area'].between(525.69, 8106.53)),
        :].reset_index(drop=True)

    print(f'The dataframe has {len(filtered_df)} rows after post-processing')
    return filtered_df



def exclude_on_location(path, name, df, buffer_distance):
    """
    Reads filtering files and creates a buffer if needed.
    Find the intersection between the prediction and polygon. Exclude these
    """
    if buffer_distance != 0:
        geojson = (gpd.read_file(path)
                    .to_crs(epsg=32633)) # the unit in buffer is meter
        
        geojson_buffer = geojson.buffer(buffer_distance)
        
        polygon = (gpd.GeoDataFrame(geometry=geojson_buffer)
                            .to_crs(crs=df.crs))
    else:
        geojson = gpd.read_file(path)
        polygon = geojson.to_crs(crs=df.crs)    

    # apply buffer function when we set buffer over 0
    if buffer > 0:
        polygon = get_geojson_with_buffer(path, df, buffer)
    else:
        polygon = get_geojson(path, df)


    intersection = sjoin(
        df,
        polygon,
        how='inner',
        predicate='intersects',
        lsuffix='_left',
        rsuffix='_right',
    )

    df.loc[:,'false_positive'] = 0

    intersection_unique = intersection[~intersection.index.duplicated(keep="first")]
    print(f'Number of barns in {name} area: {len(intersection_unique)}')

    df.loc[df.index.isin(intersection_unique.index),'false_positive']=1

    return df


def get_label_from_ee(df):
    """
    Find the terrain label for a polygon in the dataframe

    Input:
        df: a dataframe with all the information from the geojson file

    Output:
        majority_class_info['label']: the terrain label for the polygon
    """

    # The polygons are too small to get land cover data,
    # so pick a point to use (might as well be the centroid)
    centroid_df = df.centroid

    # Create a feature collection from the centroid
    fc = ee.FeatureCollection(
        ee.Feature(ee.Geometry.Point(centroid_df.x, centroid_df.y))
    )

    # Use the Dynamic World dataset
    collection = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(fc)

    # Select the 'label' band with information on the majority classification
    landcover = ee.Image(collection.first()).select("label")

    majority_class_info = landcover.reduceRegion(
        reducer=ee.Reducer.first(), geometry=fc, scale=10  # image resolution is 10m
    ).getInfo()

    return majority_class_info["label"]


def exclude_on_land_cover(filtered_df):
    """
    Add the terrain label as new column to the dataframe and filter out
    the ones that are water label(0)

    Input:
        filtered_df: a dataframe that has been filtered by the postprocess rule

    Output:
        filtered_df: a dataframe that has been filtered by the postprocess
        rule and terrain label"""
    filtered_df["terrain_label"] = filtered_df["geometry"].apply(get_label_from_ee)
    filtered_df = filtered_df[~filtered_df["terrain_label"].isin([0])]

    # Print the filtered dataframe
    print("The dataframe has", len(filtered_df), "rows after label filtering")
    return filtered_df

PATHS = ['data/geojson_to_filter_out/tl_2019_us_coastline',
         'data/geojson_to_filter_out/USA_Detailed_Water_Bodies.geojson',
         'data/geojson_to_filter_out/arcgis_FAA-Airports.geojson',
         'data/geojson_to_filter_out/us_parks_arcgis.geojson',
         'data/geojson_to_filter_out/Landscape_-_U.S._Mountain_Ranges.geojson']
         #'data/geojson_to_filter_out/municipalities___states.geoparquet',
         #'data/geojson_to_filter_out/arcgis_North_American_Roads.geojson']



def main():

    if args is None:
        raise ValueError('No arguments provided')

    # Extracts the filename and splits it to get the region code
    region_code = (os.path.basename(args.path)
                   .split('_')[0].split('/')[0])

    # Reads predictions and applies postprocess
    df = gpd.read_file(args.path)
    print(f'The original dataframe has {len(df)} rows')

    filtered_df = filter_by_postprocess_rule(df)

    # Applies our filters
    names = ['coastline',
             'water',
             'airport',
             'parks',
             'mountains']
             #'downtowns',
             #'roads']

    for name, path in zip(names, PATHS):
        filtered_df = exclude_on_location(path, name, filtered_df, args.buffer_distance)  

    if args.ee:
        filtered_df = exclude_on_land_cover(filtered_df)
    
    print(f'The dataframe has {len(filtered_df.loc[filtered_df.loc[:,'false_positive']==0,:])} rows after filtering.')
    
    # Saves in a new geojson
    filtered_df.to_file(f'output/final_data_{region_code}.geojson', driver='GeoJSON')
    print(f'The final dataframe has been saved to output/final_data_{region_code}.geojson')


if __name__ == "__main__":
    main()


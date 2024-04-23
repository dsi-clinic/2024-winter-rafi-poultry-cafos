import geopandas as gpd
import pandas as pd
import ee
import argparse as ap
from geopandas.tools import sjoin

service_account = "earth-engine-rafi@rafi-usa.iam.gserviceaccount.com"
credentials = ee.ServiceAccountCredentials(service_account, "private-key.json")
ee.Initialize(credentials)

parser = ap.ArgumentParser()
parser.add_argument("path", help="path to the file")
args = parser.parse_args()


def load_data(path):
    """
    Take in the data from the path and return a dataframe

    Input:
        path: path to the geojson file, usually the output after
          running the postprocess.py

    Output:
        df: a dataframe with all the information from the geojson file"""

    df = gpd.read_file(path)
    print("The original datafrome has", len(df), "rows")
    return df


def filter_by_postprocess_rule(df):
    """
    Filter the dataframe by the postprocess rule

    Input:
        df: a dataframe with all the information from the geojson file

    Output:
        filtered_df: a dataframe that has been filtered by the postprocess rule"""

    filtered_df = df.loc[df.rectangle_aspect_ratio.between(3.4, 20.49)].reset_index(
        drop=True
    )
    filtered_df = filtered_df.loc[
        filtered_df.distance_to_nearest_road != 0
    ].reset_index(drop=True)
    filtered_df = filtered_df.loc[filtered_df["area"].between(525.69, 8106.53)]
    print("The dataframe has", len(filtered_df), "rows after post-processing")
    return filtered_df


def get_geojson(path, df):
    """
    get the shapefile of downtown areas.
    """

    geojson = gpd.read_file(path)

    polygon = geojson.to_crs(df.crs)
    return polygon


def get_geojson_with_buffer(path, df, buffer_distance):
    """
    get areas that are within a specified buffer distance.
    """
    # Create a buffer around the geojson
    geojson = gpd.read_file(path)
    # convert to crs where the unit in buffer is meter
    geojson_data = geojson.to_crs(epsg=32633)
    geojson_buffer = geojson_data.buffer(buffer_distance)
    geojson_buffer_gdf = gpd.GeoDataFrame(geometry=geojson_buffer)
    # match crs
    geojson_buffer_gdf = geojson_buffer_gdf.to_crs(df.crs)
    return geojson_buffer_gdf




def exclude_on_location(df, path, name, buffer=0):
    """
    find the intersection between the predictions
      and polygon and exclude these predictions
    """

    # apply buffer function when we set buffer over 0
    if buffer > 0:
        polygon = get_geojson_with_buffer(path, df, buffer)
    else:
        polygon = get_geojson(path, df)


    intersection = sjoin(
        df,
        polygon,
        how="inner",
        predicate="intersects",
        lsuffix="_left",
        rsuffix="_right",
    )
    # remove duplicated index in intesection
    intersection_unique = intersection[~intersection.index.duplicated(keep="first")]
    print(f"Number of barns in {name} area:", len(intersection_unique))
    filtered_df = df[~df.index.isin(intersection_unique.index)].copy()

    return filtered_df


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


def save_to_geojson(filtered_df):
    filtered_df.to_file("output/final_data.geojson", driver="GeoJSON")
    print("The final dataframe has been saved to output/final_data.geojson")
    return None


def main(ee=False):
    df = load_data(args.path)
    # get polygon information
    #downtown_polygon = gpd.read_parquet('data/geojson_to_filter_out/municipalities___states.geoparquet')

    # run Microsoft's preprocessing
    filtered_df = filter_by_postprocess_rule(df)
    # run the exclusion rules

    filtered_df = exclude_on_location(filtered_df, 'data/geojson_to_filter_out/tl_2019_us_coastline', 'coastline', 150)
    filtered_df = exclude_on_location(filtered_df, 'data/geojson_to_filter_out/USA_Detailed_Water_Bodies.geojson', 'water')
    filtered_df = exclude_on_location(filtered_df, 'data/geojson_to_filter_out/arcgis_FAA-Airports.geojson', 'airport', 1500)
    filtered_df = exclude_on_location(filtered_df, 'data/geojson_to_filter_out/us_parks_arcgis.geojson', 'parks')
    filtered_df = exclude_on_location(filtered_df, 'data/geojson_to_filter_out/Landscape_-_U.S._Mountain_Ranges.geojson', 'mountains')
    filtered_df = exclude_on_location(filtered_df, 'data/geojson_to_filter_out/arcgis_North_American_Roads.geojson', 'roads', 100)


    if ee:
        filtered_df = exclude_on_land_cover(filtered_df)
    print(
        "The dataframe has",
        len(filtered_df),
        "rows after removing downtown, water, coastline, airport, roads and mountains area.",
    )
    # save to the output folder
    save_to_geojson(filtered_df)


if __name__ == "__main__":
    main()

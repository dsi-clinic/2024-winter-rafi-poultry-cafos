import ipyleaflet as ileaflet
import ipywidgets as widgets
from IPython.display import display, clear_output
import geopandas as gpd
import pandas as pd
import os

def classify_poultry_barns(geojson_path):
    # Load the GeoJSON data
    poultry_barns = gpd.read_file(geojson_path)

    if not os.path.exists('/content/2024-winter-rafi-poultry-cafos/output/checked_barns_indices.txt'):
        with open('/content/2024-winter-rafi-poultry-cafos/output/checked_barns_indices.txt', 'w') as file:
            checked_indices = []

    with open('/content/2024-winter-rafi-poultry-cafos/output/checked_barns_indices.txt', 'r') as file:
        lines = file.readlines()
    checked_indices = [(int(line.strip().split(',')[0]), int(line.strip().split(',')[1])) for line in lines]

    poultry_barns = poultry_barns[poultry_barns['false_positive'] != 1]
    ori_length = len(poultry_barns)
    already_checked_list = [i[0] for i in checked_indices]
    poultry_barns = poultry_barns[~poultry_barns.index.isin(already_checked_list)]

    def handle_classification(button, result):
        index = button.index
        checked_indices.append((index, result))
        with open('/content/2024-winter-rafi-poultry-cafos/output/checked_barns_indices.txt', 'a') as file:
            file.write(f'{index}, {result}\n')

        clear_output(wait=True)
        print(f"Barns remaining: {ori_length - len(checked_indices)}")
        next_index = index + 1
        if next_index < len(poultry_barns):
            display_location(next_index)
        else:
            print("All locations have been reviewed.")

    def display_location(index):
        m = ileaflet.Map(zoom=18, basemap=ileaflet.basemaps.Esri.WorldImagery)
        feature = poultry_barns.iloc[index]
        coords = feature.geometry.exterior.coords.xy
        centroid = (sum(coords[1]) / len(coords[1]), sum(coords[0]) / len(coords[0]))
        m.center = centroid
        m.layers = [m.layers[0]]  # Keep the base map only

        polygon = ileaflet.Polygon(locations=[(y, x) for x, y in zip(*coords)], color="red", fill_color="red")
        m.add_layer(polygon)

        button_style = widgets.Layout(width='200px', height='50px', margin='5px')
        btn_true_positive = widgets.Button(description='True Positive', button_style='success', layout=button_style)
        btn_true_negative = widgets.Button(description='False Positive', button_style='warning', layout=button_style)
        btn_true_positive.on_click(lambda b: handle_classification(b, 1))
        btn_true_negative.on_click(lambda b: handle_classification(b, 0))
        btn_true_positive.index = index
        btn_true_negative.index = index
        btn_true_positive.centroid = centroid
        btn_true_negative.centroid = centroid

        button_box = widgets.VBox([btn_true_positive, btn_true_negative], layout=widgets.Layout(align_items='center'))
        display(widgets.HBox([m, button_box], layout=widgets.Layout(align_items='center', justify_content='space-between')))

    if not poultry_barns.empty:
        display_location(poultry_barns.index[0])
    else:
        print("All locations have been reviewed.")

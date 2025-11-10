import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import json
import os
import folium
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import base64


def site_import(file_path, parameter=None):
    """Import sites from Excel, clean data, and convert to GeoDataFrame"""
    
    sites = pd.read_excel(file_path)
    sites = sites.iloc[:-1]  # Drop last row
   
    # Rename columns
    sites = sites.rename(columns={
        "SITE_CODE": "site", 
        "SITE_NAME": "site_name", 
        "DATE_INSTA": "date installed",
        "LAT": "latitude", 
        "LON": "longitude", 
        "GAGETAG": "parameter",
        "Program supporting": "program",
        "ISP site notes": "notes",
        'Annual equipment cost (Replacement cost of both types of gages Data logger and monitoring sensors=$4100 2025 cost.  10 year lifetime of equipment.  Ammortized yearly replacement cost $410)': "annual equipment cost"
    })
    
    # Standardize parameter names
    parameter_mapping = {
        'Precipitation Gauge(Recording)': 'precipitation',
        'Stream Gauge(Recording with Discharge)': 'discharge',
        'Water Temperature Recorder': 'water_temperature'
    }
    sites["parameter"] = sites["parameter"].replace(parameter_mapping)
    
    # Select relevant columns
    sites = sites[[
        "site", "site_name", "parameter", "latitude", "longitude", 
        "WRIA", "program", "notes", "Yearly Hours", "KM verified", 
        "KM notes", "annual equipment cost", "date installed", "WTD vs SWM"
    ]]
    
    # Validate coordinates exist
    if 'latitude' not in sites.columns or 'longitude' not in sites.columns:
        raise ValueError("Excel file must contain 'latitude' and 'longitude' columns")
    
    # Drop rows with missing coordinates
    sites = sites.dropna(subset=['longitude', 'latitude'])
    
    # Create GeoDataFrame
    site_points = [Point(lon, lat) for lon, lat in zip(sites['longitude'], sites['latitude'])]
    sites_gdf = gpd.GeoDataFrame(sites, geometry=site_points, crs='EPSG:4326')
    return sites_gdf


def wtd_service_area_import():
    """Import WTD service area boundary"""
    os.environ['OGR_GEOJSON_MAX_OBJ_SIZE'] = '0'
    full_gdf = gpd.read_file("C:/Users/IHiggins/OneDrive - King County/cache_render_gis_data/WTD_service_area.geojson")
    full_gdf = full_gdf.to_crs("EPSG:4326")
    return full_gdf


def basin_import():
    """Import or download watershed basins from King County GIS"""
    cache_path = "C:/Users/ihiggins/OneDrive - King County/cache_render_gis_data/watersheds.geojson"
    
    if os.path.exists(cache_path):
        print("Loading cached watersheds")
        return gpd.read_file(cache_path)
    
    print("Downloading watersheds from King County GIS")
    try:
        geojson_url = "https://gisdata.kingcounty.gov/arcgis/rest/services/OpenDataPortal/enviro___base/MapServer/237/query?outFields=*&where=1%3D1&f=geojson"
        watersheds = gpd.read_file(geojson_url)
        watersheds = watersheds.to_crs('EPSG:4326')
        watersheds = watersheds.drop(columns=["OBJECTID_1", "CONDITION"], errors='ignore')
        watersheds = watersheds.rename(columns={"STUDY_UNIT": "basin"})
        watersheds = watersheds.set_index("OBJECTID")
        watersheds.to_file(cache_path, driver="GeoJSON")
        return watersheds
    except Exception as e:
        print(f"Error fetching watersheds: {e}")
        return None


def filter_site_basins(sites_gdf, watersheds):
    """Assign basin to each site using spatial join"""
    sites_gdf = gpd.sjoin(sites_gdf, watersheds, how='left', predicate='intersects')
    sites_gdf = sites_gdf.drop(columns=["index_right"], errors='ignore')
    return sites_gdf


def wtd_basins(sites_gdf, basins, wtd_service_area, intersect_fraction):
    """Filter basins to those in WTD service area and mark sites accordingly"""
    #wtd_basins = basins[basins.intersects(wtd_service_area.union_all())]
    # Union all service areas into a single geometry
    # Assuming both are GeoDataFrames in the same CRS
    projected_crs = "EPSG:2285"  # good for King County / Seattle area

    basins_proj = basins.to_crs(projected_crs)
    wtd_service_area_proj = wtd_service_area.to_crs(projected_crs)

    # Union all service area polygons into one
    wtd_union = wtd_service_area_proj.unary_union

    # Compute intersection areas and area fractions
    basins_proj["intersect_area"] = basins_proj.geometry.intersection(wtd_union).area
    basins_proj["basin_area"] = basins_proj.geometry.area
    basins_proj["intersect_frac"] = basins_proj["intersect_area"] / basins_proj["basin_area"]
    basins_proj["intersect_frac"] = basins_proj["intersect_frac"].round(2)
    # Filter for basins where 50% or more overlaps
    wtd_basins = basins_proj[basins_proj["intersect_frac"] >= intersect_fraction]

    # (Optional) convert back to your original CRS for mapping
    wtd_basins = wtd_basins.to_crs(basins.crs)

    wtd_basins = wtd_basins[wtd_basins.intersects(sites_gdf.union_all())]
    
    sites_gdf['WTD Service Area'] = sites_gdf.geometry.apply(
        lambda point: wtd_basins.intersects(point).any()
    )
    # add intersect fract to sites
    from shapely.ops import nearest_points

    def get_intersect_frac(point, basins):
        for _, basin in basins.iterrows():
            if basin.geometry.intersects(point):
                return basin["intersect_frac"]
        return None

    sites_gdf["Intersect_Frac"] = sites_gdf.geometry.apply(lambda p: get_intersect_frac(p, wtd_basins))
    
    return wtd_basins, sites_gdf


def add_map_legend(m, layer_name='WTD Sites', show=True):
    """Add legend to map"""
    legend_html = f'''
    <div id="parameter-legend" style="
        position: fixed; bottom: 10px; left: 10px; width: 250px;
        background-color: white; opacity: 0.9; border: 2px solid grey; border-radius: 5px;
        padding: 10px; font-size: 14px; z-index: 9999;
        box-shadow: 2px 2px 6px rgba(0,0,0,0.3); display: none;">
        <h4 style="margin: 0 0 10px 0; font-size: 16px;">WTD Sites by Parameter</h4>
        <div style="margin: 5px 0;">
            <span style="display: inline-block; width: 12px; height: 12px; 
                         background-color: #00A5E2; border-radius: 50%; margin-right: 8px;"></span>
            Stream Gage Sites
        </div>
        <div style="margin: 5px 0;">
            <span style="display: inline-block; width: 12px; height: 12px; 
                         background-color: #66c597; border-radius: 50%; margin-right: 8px;"></span>
            Rain Gage Sites
        </div>
        <hr style="border: none; border-top: 3px solid #74737A; margin: 5px 0;">
        <div style="margin: 5px 0;">
            <span style="display: inline-block; width: 20px; height: 0px; 
                        border-top: 3px dashed #FFBF65; margin-right: 8px; vertical-align: middle;"></span>
            WTD Service Area
        </div>
    </div>
    
    <script>
        function toggleLegend() {{
            var legend = document.getElementById('parameter-legend');
            var layerControl = document.querySelector('.leaflet-control-layers-overlays');
            
            if (layerControl) {{
                var inputs = layerControl.querySelectorAll('input[type="checkbox"]');
                inputs.forEach(function(input) {{
                    var label = input.parentElement.querySelector('span').textContent.trim();
                    if (label === "{layer_name}") {{
                        legend.style.display = input.checked ? 'block' : 'none';
                    }}
                }});
            }}
        }}
        
        setTimeout(toggleLegend, 500);
        document.addEventListener('click', function(e) {{
            if (e.target.type === 'checkbox') {{
                setTimeout(toggleLegend, 100);
            }}
        }});
        {'setTimeout(function() { document.getElementById("parameter-legend").style.display = "block"; }, 500);' if show else ''}
    </script>
    '''
    
    m.get_root().html.add_child(folium.Element(legend_html))
    return m

def add_isp_map_legend(m, layer_name='ISP Sites', show=True):
    """Add legend to map"""
    #  # isp = '#fee08b'  # or blue #8bc9fe non isp = '#D53E4F'
    legend_html = f'''
    <div id="parameter-legend" style="
        position: fixed; bottom: 10px; left: 10px; width: 250px;
        background-color: white; opacity: 0.9; border: 2px solid grey; border-radius: 5px;
        padding: 10px; font-size: 14px; z-index: 9999;
        box-shadow: 2px 2px 6px rgba(0,0,0,0.3); display: none;">
        <h4 style="margin: 0 0 10px 0; font-size: 16px;">ISP Sites</h4>
        <div style="margin: 5px 0;">
            <span style="display: inline-block; width: 12px; height: 12px; 
                         background-color: #e48448; border-radius: 50%; margin-right: 8px;"></span>
            New ISP Sites
        </div>
        <div style="margin: 5px 0;">
            <span style="display: inline-block; width: 12px; height: 12px; 
                         background-color: #e44848; border-radius: 50%; margin-right: 8px;"></span>
            New ISP and WQI Sites
        </div>
        <div style="margin: 5px 0;">
            <span style="display: inline-block; width: 12px; height: 12px; 
                         background-color: #b2b2b5; border-radius: 50%; margin-right: 8px;"></span>
            WTD Non ISP Sites
        </div>
        <div style="margin: 5px 0;">
            <span style="display: inline-block; width: 12px; height: 12px; 
                         background-color: #487ee4; border-radius: 50%; margin-right: 8px;"></span>
            SWM Funded ISP Sites
        </div>
        <hr style="border: none; border-top: 3px solid #74737A; margin: 5px 0;">
        <div style="margin: 5px 0;">
            <span style="display: inline-block; width: 20px; height: 0px; 
                        border-top: 3px dashed #FFBF65; margin-right: 8px; vertical-align: middle;"></span>
            WTD Service Area
        </div>
    </div>
    
    <script>
        function toggleLegend() {{
            var legend = document.getElementById('parameter-legend');
            var layerControl = document.querySelector('.leaflet-control-layers-overlays');
            
            if (layerControl) {{
                var inputs = layerControl.querySelectorAll('input[type="checkbox"]');
                inputs.forEach(function(input) {{
                    var label = input.parentElement.querySelector('span').textContent.trim();
                    if (label === "{layer_name}") {{
                        legend.style.display = input.checked ? 'block' : 'none';
                    }}
                }});
            }}
        }}
        
        setTimeout(toggleLegend, 500);
        document.addEventListener('click', function(e) {{
            if (e.target.type === 'checkbox') {{
                setTimeout(toggleLegend, 100);
            }}
        }});
        {'setTimeout(function() { document.getElementById("parameter-legend").style.display = "block"; }, 500);' if show else ''}
    </script>
    '''
    
    m.get_root().html.add_child(folium.Element(legend_html))
    return m

def add_sites_colored_by_parameter(m, sites_gdf, layer_name='Sites by Parameter', show=True, radius=6):
    """Add sites to map with colors based on parameter type"""
    if sites_gdf.empty:
        return m
    
    # Color mapping
    parameter_colors = {
        'discharge': '#00A5E3',
        'water_temperature': '#E77577',
        'precipitation': '#8DD7BF',
        'nan': 'gray',
        'unknown': 'gray'
    }
    
    sites_layer = folium.FeatureGroup(name=layer_name, show=show)
    
    for idx, row in sites_gdf.iterrows():
        # Get site information
        site = row.get('site', 'N/A')
        site_name = row.get('site_name', 'N/A')
        parameter = row.get('parameter', 'unknown')
        wria = row.get('WRIA', 'N/A')
        program = row.get('program', 'N/A')
        notes = row.get('notes', '')
        
        # Determine color
        if pd.isna(parameter):
            color = parameter_colors['nan']
            parameter = 'N/A'
        else:
            color = parameter_colors.get(parameter, 'gray')
        
        # Create popup and tooltip
        popup_text = f"""
            <b>Site: {site}</b><br>
            Site Name: {site_name}<br>
            Parameter: {parameter}<br>
            WRIA: {wria}<br>
            Program: {program}<br>
            Notes: {notes}
        """
        tooltip_text = f"{site} {site_name}"
        
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=radius,
            popup=folium.Popup(popup_text, max_width=300),
            tooltip=folium.Tooltip(tooltip_text, permanent=False),  
            color=color,
            fillColor=color,
            fillOpacity=1,
            weight=0,
        ).add_to(sites_layer)
    
    sites_layer.add_to(m)
    return m


def add_filtered_sites(m, sites_gdf, parameter_filter=None, program_filter=None, 
                       exclude_empty_notes=False, layer_name='Sites', 
                       color='black', show=True, radius=5):
    """Add filtered sites to map"""
    if sites_gdf.empty:
        return m
    
    filtered_sites = sites_gdf.copy()
    
    # Apply filters
    if parameter_filter is not None:
        if isinstance(parameter_filter, str):
            parameter_filter = [parameter_filter]
        filtered_sites = filtered_sites[filtered_sites['parameter'].isin(parameter_filter)]
    
    if program_filter is not None:
        #if isinstance(program_filter, str):
        #    program_filter = [program_filter]
        filtered_sites = filtered_sites[filtered_sites['program'] == program_filter]
    
    if exclude_empty_notes:
        filtered_sites = filtered_sites[
            filtered_sites['notes'].notna() & 
            (filtered_sites['notes'].astype(str).str.strip() != '')
        ]
    
    if filtered_sites.empty:
        return m
    
    sites_layer = folium.FeatureGroup(name=layer_name, show=show)
    
    for idx, row in filtered_sites.iterrows():
        popup_text = f"""
            <b>Site: {row.get('site', 'N/A')}</b><br>
            Site Name: {row.get('site_name', 'N/A')}<br>
            Parameter: {row.get('parameter', 'N/A')}<br>
            WRIA: {row.get('WRIA', 'N/A')}<br>
            Program: {row.get('program', 'N/A')}<br>
            Notes: {row.get('notes', '')}
        """
        
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=radius,
            popup=folium.Popup(popup_text, max_width=300),
            tooltip=f"Site: {row.get('site', 'N/A')}",
            color=color,
            fillColor=color,
            fillOpacity=1,
            weight=0,
        ).add_to(sites_layer)
    
    sites_layer.add_to(m)
    return m


def create_map(sites_gdf, wtd_service_area, wtd_basins):
    """Create Folium map with sites and WTD service area"""
    
    # Center map on sites
    """bounds = sites_gdf.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2"""
    # set bounds to WTD service area
    bounds = wtd_service_area.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2
    
    # Create base map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=10,
        zoom_control=True,
        scrollWheelZoom=True,
        doubleClickZoom=True,
        tiles=None
    )
    
    # Add base layers
    folium.TileLayer(
        tiles='OpenStreetMap',
        name='Street Map',
        overlay=False,
        control=True,
        show = False,
    ).add_to(m)
    # Add base layers
    folium.TileLayer(
        tiles="Cartodb Positron",
        name='Simple Carto',
        overlay=False,
        control=True,
        show = True,
    ).add_to(m)
    
 
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Satellite',
        overlay=False,
        control=True,
        show=False
    ).add_to(m)
    
    # Add WTD service area boundary
    if wtd_service_area is not None and not wtd_service_area.empty:
        wtd_layer = folium.FeatureGroup(name='WTD Service Area', show=True)
        folium.GeoJson(
            wtd_service_area,
            style_function=lambda x: {
                'fillColor': 'transparent',
                'color': '#FFBF65',
                'weight': 3,
                'dashArray': '10, 5',
                'fillOpacity': 0
            },
            tooltip="WTD Service Area Boundary"
        ).add_to(wtd_layer)
        wtd_layer.add_to(m)
    
    # Add WTD basins
    if wtd_basins is not None and not wtd_basins.empty:
        wtd_basin_layer = folium.FeatureGroup(name='WTD Basins', show=False)
        folium.GeoJson(
            wtd_basins,
            style_function=lambda x: {
                'fillColor': '#20B2AA',
                'color': 'black',
                'weight': 1,
                'fillOpacity': 0.5
            },
            tooltip="WTD Basins"
        ).add_to(wtd_basin_layer)
        wtd_basin_layer.add_to(m)
    
    # Add sites
    # https://wondernote.org/color-palettes-for-web-digital-blog-graphic-design-with-hexadecimal-codes/
    #wtd_sites = sites_gdf[sites_gdf["WTD Service Area"] == True]
    #add_sites_colored_by_parameter(m, sites_gdf, layer_name='Sites by Parameter', show=True, radius=6)
    # discharge sites
    discharge_sites = sites_gdf[(sites_gdf["parameter"] == "discharge") & (sites_gdf["WTD vs SWM"] == "WTD")]
    non_discharge_sites = sites_gdf[(sites_gdf["parameter"] != "discharge") & (sites_gdf["WTD vs SWM"] == "WTD")]
   
    #add_filtered_sites(m, non_wtd_sites, layer_name='Non WTD Sites', color='#969696', show=True, radius=6)
    add_filtered_sites(m, discharge_sites, layer_name='Stream Gage Sites', color='#00A5E2', show=True, radius=6)
    add_filtered_sites(m, non_discharge_sites, layer_name='Rain Gage Sites', color='#66c597', show=True, radius=6)
    # discharge '#00A5E2' other stream gage ##8DD7BF #e4a248'#8DD7BF'
    # Add legend
    add_map_legend(m, layer_name='discharge sites', show=True)
    add_map_legend(m, layer_name='other stream gage sites', show=True)
    # Add layer control
    folium.LayerControl(collapsed=False, show=False).add_to(m)
    
    return m

def create_isp_map(sites_gdf, wtd_service_area, wtd_basins):
    """Create Folium map with sites and WTD service area"""
    # filter out non wtd sites
    #wtd_sites = sites_gdf[sites_gdf["WTD Service Area"] == True]
    # Center map on sites
    bounds = sites_gdf.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2
    
    # Create base map
    m = folium.Map(
        location=[center_lat, center_lon],  #center_lat+0.05 moves up/north a bit
        zoom_start=10,
        zoom_control=True,
        scrollWheelZoom=True,
        doubleClickZoom=True,
        tiles=None
    )
    folium.TileLayer(
        tiles="Cartodb Positron",
        name='Simple Carto',
        overlay=False,
        control=True,
        show = True,
    ).add_to(m)
    # Add base layers
    folium.TileLayer(
        tiles='OpenStreetMap',
        name='Street Map',
        overlay=False,
        control=True,
        show=False,
    ).add_to(m)
    
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Satellite',
        overlay=False,
        control=True,
        show=False
    ).add_to(m)
    
    # Add WTD service area boundary
    if wtd_service_area is not None and not wtd_service_area.empty:
        wtd_layer = folium.FeatureGroup(name='WTD Service Area', show=True)
        folium.GeoJson(
            wtd_service_area,
            style_function=lambda x: {
                'fillColor': 'transparent',
                'color': '#efcb91',
                'weight': 3,
                'dashArray': '10, 5',
                'fillOpacity': 0
            },
            tooltip="WTD Service Area Boundary"
        ).add_to(wtd_layer)
        wtd_layer.add_to(m)
    # old orange #FFBF65 new green #48e48c # yellow
    # Add WTD basins
    if wtd_basins is not None and not wtd_basins.empty:
        wtd_basin_layer = folium.FeatureGroup(name='WTD Basins', show=False)
        folium.GeoJson(
            wtd_basins,
            style_function=lambda x: {
                'fillColor': '#20B2AA',
                'color': 'black',
                'weight': 1,
                'fillOpacity': 0.5
            },
            tooltip="WTD Basins"
        ).add_to(wtd_basin_layer)
        wtd_basin_layer.add_to(m)
    
    # Add sites
    #wtd_sites = sites_gdf[sites_gdf["WTD Service Area"] == True]
    #add_sites_colored_by_parameter(m, wtd_sites, layer_name='Sites by Parameter', show=True, radius=6)
    
    
    #add_filtered_sites(m, wtd_sites, parameter_filter=None, program_filter="ISP", 
    #                   exclude_empty_notes=False, layer_name='ISP Sites', 
    #                   color='grey', show=True, radius=5)

    # New WTD ISP sites
    # New WTD ISP/WQI sites
    #  Non ISP sites
    # SWM ISP sites

    #Sites Supporting ISP, WQBE and WQI  Orange #F58427
    #Sites Supporting WQI and other programs  tellow # D5C12A
    #SWM Funded ISP Site  Blue #23AFA5

    
    isp_wqbe_wqi = sites_gdf.loc[(sites_gdf["program"] == "Sites Supporting ISP, WQBE and WQI")]
    wqi = sites_gdf.loc[(sites_gdf["program"] == "Sites Supporting WQI and other programs")]
    swm = sites_gdf.loc[(sites_gdf["program"] == "SWM Funded ISP Site")]
    
    #Sites Supporting ISP, WQBE and WQI  Orange
    add_filtered_sites(m, isp_wqbe_wqi, parameter_filter=None, program_filter=None, 
                       exclude_empty_notes=False, layer_name="Sites Supporting ISP, WQBE and WQI", 
                       color='#F58427', show=True, radius=5)
    # Add legend
    add_isp_map_legend(m, layer_name="Sites Supporting ISP, WQBE and WQI", show=True)

    #Sites Supporting WQI and other programs
    add_filtered_sites(m, wqi, parameter_filter=None, program_filter=None, 
                       exclude_empty_notes=False, layer_name="Sites Supporting WQI and other programs", 
                       color='#D5C12A', show=True, radius=5)
    # Add legend
    add_isp_map_legend(m, layer_name="Sites Supporting WQI and other programs", show=True)
    
    #SWM funded ISP
    add_filtered_sites(m, swm, parameter_filter=None, program_filter=None, 
                       exclude_empty_notes=False, layer_name="SWM Funded ISP Site", 
                       color='#23AFA5', show=True, radius=5)
    # Add legend
    add_isp_map_legend(m, layer_name="SWM Funded ISP Site", show=True)
            
    # isp = '#FFEC59' or blue #8bc9fe non isp = '#00B0BA'
    #non_wtd_sites = sites_gdf[sites_gdf["WTD Service Area"] == False]
    #add_filtered_sites(m, non_wtd_sites, layer_name='Non WTD Sites', color='#969696', show=True, radius=6)
    
    
    # Add layer control
    folium.LayerControl(collapsed=False, show=False).add_to(m)
    
    return m
def save_map_screenshot(html_path, output_path, pdf_path, window_size=(729, 943)):
    """Save map as static PNG screenshot"""
    
    # Read original HTML
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Create static version
    static_code = """
    <style>
    .leaflet-container {
        cursor: default !important;
        pointer-events: none !important;
    }
    .leaflet-control-zoom,
    .leaflet-control-attribution,
    .leaflet-control-layers {
        display: none !important;
    }
    </style>
    </head>
    """
    
    static_html = html_content.replace('</head>', static_code)
    
    # Save static version to temporary file
    static_html_path = html_path.replace('.html', '_static.html')
    with open(static_html_path, 'w', encoding='utf-8') as f:
        f.write(static_html)
    
    # Take screenshot of static version
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument(f'--window-size={window_size[0]},{window_size[1]}')
    
    driver = webdriver.Chrome(options=chrome_options)
    html_uri = Path(static_html_path).resolve().as_uri()
    driver.get(html_uri)
    time.sleep(2)
    driver.save_screenshot(output_path)
  

    

    # Wait for page to render (optional)
    time.sleep(2)

    # Use Chrome DevTools Protocol (CDP) to print to PDF
    pdf = driver.execute_cdp_cmd("Page.printToPDF", {
        "printBackground": True,
        "landscape": False
    })

    # Save the base64-encoded PDF data to file
    with open(pdf_path, "wb") as f:
        f.write(base64.b64decode(pdf['data']))

    driver.quit()

   
    # Optionally remove temporary static file
    # os.remove(static_html_path)


# Main execution
if __name__ == "__main__":
    # Import data
    #sites_gdf = site_import(file_path="WTD_map/data/WTD_LTM_Gages.xlsx")
    sites_gdf = site_import(file_path="data/WTD_LTM_Gages.xlsx")
    wtd_service_area = wtd_service_area_import()
    basins = basin_import()
    
    # Process data
    sites_gdf = filter_site_basins(sites_gdf, basins)
    basins_filter, sites_gdf = wtd_basins(sites_gdf, basins, wtd_service_area, intersect_fraction = 0.10)
    
    # Create and save map
    m = create_map(sites_gdf, wtd_service_area, basins_filter)
    m.save("data/wtd_map.html")
    print(sites_gdf.columns)
    # Export processed sites to CSV
    output_cols = [
        "site", "site_name", "parameter", "date installed", "latitude", "longitude",
        "WRIA", "basin", "WTD Service Area","Intersect_Frac", "program", "notes", 
        "Yearly Hours", "KM verified", "KM notes", "annual equipment cost", "WTD vs SWM"
    ]
    sites_gdf[output_cols].to_csv("data/WTD_LTM_Gages_Modified.csv", index=False)
    
    # Save screenshot
    save_map_screenshot(
        html_path='data/wtd_map.html',
        output_path='data/wtd_map.png',
        pdf_path='data/wtd_map.pdf',
        window_size=(729, 943)
    )
    
    # remove wtd basins from mapping
    basins_filter = None
   

    ### create filterd isp map
    m = create_isp_map(sites_gdf, wtd_service_area, basins_filter)
    m.save("data/isp_map.html")

    # Save screenshot
    save_map_screenshot(
        html_path='data/isp_map.html',
        output_path='data/isp_map.png',
        pdf_path='data/isp_map.pdf',
        window_size=(729, 943)
    )
    print("Map generation complete!")
    print(f"Sites processed: {len(sites_gdf)}")
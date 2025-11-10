# transect entry table default rows
import numpy as np
from dash_ag_grid import AgGrid


def transect_entry_grid():
    return  AgGrid(
        id='transect_entry_table',
        columnDefs=[
            {"field": "id", "headerName": "id", "editable": False, "hide": True, "flex": 1, "cellEditor": "agNumberCellEditor", "cellEditorParams": {"min": 0}},
            {"field": "location", "headerName": "location", "editable": True, "flex": 1, "cellEditor": "agNumberCellEditor", "cellEditorParams": {"min": 0}},
            {"field": "depth", "headerName": "depth", "editable": True, "flex": 1, "cellEditor": "agNumberCellEditor", "cellEditorParams": {"min": 0}},
            {"field": "velocity", "headerName": "velocity", "editable": True, "flex": 1, "cellEditor": "agNumberCellEditor", "cellEditorParams": {"min": 0}},
            {"field": "angle", "headerName": "angle", "editable": True, "flex": 1, "cellEditor": "agNumberCellEditor", "cellEditorParams": {"min": 0}},
        ],
        columnSize="sizeToFit",
        defaultColDef={"sortable": False},
        dashGridOptions= {
            "rowSelection": "single",
            "deltaRowDataMode": True,
            "enterMovesDown": True,
            "enterMovesDownAfterEdit": True,
            "stopEditingWhenCellsLoseFocus": True,
            "function": "params => params.nextCellPosition",
            "columnSizeAuto": "function (params) { params.api.sizeColumnsToFit(); }",
            "singleClickEdit": True,
            
                },
        getRowId="params.data.id", 
        style={"height": "300px", "width": "100%"},
    )
def transect_entry_table_default_rows():
    """ returns default rows and values for transect entry table"""
    return {
        "id": 0,
        "location": np.nan,
        "depth": np.nan,
        "velocity": np.nan,
        "angle": 1
        
        
    }
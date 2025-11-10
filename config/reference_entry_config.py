import numpy as np
from dash_ag_grid import AgGrid

def reference_entry_grid():
     return AgGrid(
        id='reference-location-table',
        columnDefs=[
            {"field": "id", "headerName": "id", "editable": False, "hide": True},
            {"field": "site", "headerName": "site", "editable": False},
            {"field": "parameter", "headerName": "parameter", "editable": True},
            {"field": "reference_location", "headerName": "reference_location", "editable": True},
            {"field": "reference", "headerName": "reference", "editable": True},
            {"field": "notes", "headerName": "notes", "editable": True},
        ],
        columnSize="sizeToFit",
        dashGridOptions={"rowSelection": "single"},
        style={"height": "300px", "width": "100%"},
    )
def column_defs_no_edit():
    return [
            {"field": "site", "headerName": "site", "editable": False, "hide": False},
            {"field": "parameter", "headerName": "parameter", "editable": True},
            {"field": "location", "headerName": "location", "editable": True},
            {"field": "project", "headerName": "project", "editable": True},
            {"field": "notes", "headerName": "notes", "editable": True},
        ]

def column_defs_edit():
    return [
            {"field": "site", "headerName": "site", "editable": True, "hide": False},
            {"field": "parameter", "headerName": "parameter", "editable": True},
            {"field": "location", "headerName": "location", "editable": True},
            {"field": "project", "headerName": "project", "editable": True},
            {"field": "notes", "headerName": "notes", "editable": True},
        ]
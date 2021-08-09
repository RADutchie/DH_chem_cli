"""Functions to load and filter input geochem data to a single element dataset"""

import dask.dataframe as dd
import pandas as pd
from pathlib import Path


def clean_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Remove non-numeric characters.

    Clean non-numeric characters from dataframe and flag below detection
    limit rows (1), and greater than measurable rows (2) in new BDL column.

    Args:
        df (pd.DataFrame): Input dataframe to clean.

    Returns:
        pd.DataFrame: Cleaned dataframe
    """
    df.drop(df[df.VALUE.str.contains(r"-", na=False, regex=False)].index, inplace=True)

    # create BDL/ODL flag and remove strings from values
    df["BDL"] = 0
    df.loc[df["VALUE"].str.contains("<", na=False, regex=False), "BDL"] = 1
    df.loc[df["VALUE"].str.contains(">", na=False, regex=False), "BDL"] = 2
    df["VALUE"] = (
        df["VALUE"].astype(str).str.replace(r"[<>]", "", regex=True).astype(float)
    )

    return df


def convert_oxides(df: pd.DataFrame, element: str) -> pd.DataFrame:
    """Convert selected oxides to elements

    Args:
        df (pd.DataFrame): Input dataframe
        element (str): Oxide to convert. Can be any of:
        'Fe2O3', 'FeO', 'U3O8', 'CoO', 'NiO'

    Returns:
        pd.DataFrame: Dataframe with oxides converted in place
    """
    df = df

    if element == "Fe2O3":
        df["VALUE"] = df["VALUE"] / 1.4297
    elif element == "FeO":
        df["VALUE"] = df["VALUE"] / 1.2865
    elif element == "U3O8":
        df["VALUE"] = df["VALUE"] / 1.1792
    elif element == "CoO":
        df["VALUE"] = df["VALUE"] / 1.2715
    elif element == "NiO":
        df["VALUE"] = df["VALUE"] / 1.2725
    else:
        pass

    return df


def convert_ppm(df: pd.DataFrame, element: str) -> pd.DataFrame:
    """Convert units to ppm, and below detection limit values to low, non-zero, values.

    Args:
        df (pd.DataFrame): Input dataframe
        element (str): Element

    Returns:
        pd.DataFrame: Dataframe with new 'converted_ppm' column
    """
    df = df

    df["converted_ppm"] = df["VALUE"]
    df.loc[(df["UNIT"] == "%"), "converted_ppm"] = (
        df.loc[(df["UNIT"] == "%"), "VALUE"] * 10000
    )

    df.loc[(df["UNIT"] == "ppb"), "converted_ppm"] = (
        df.loc[(df["UNIT"] == "ppb"), "VALUE"] / 10000
    )

    # convert the BDL values to low but non-zero values
    if element == "Au" or element == "Ag":
        df.loc[
            df["BDL"] == 1, "converted_ppm"
        ] = 0.00001  # convert bdl values to 0.01ppb for Au and Ag
    else:
        df.loc[df["BDL"] == 1, "converted_ppm"] = 0.001

    return df


def add_chem_method(df: pd.DataFrame) -> pd.DataFrame:
    """Add normalised chem method columns to dataset.

    Function to map normalised chem method types onto the SARIG CHEM_METHOD_CODE column.
    The chem methods provided in the SARIG dataset relate to individual lab codes. This
    function maps those codes, where known, to a generic analysis method, digestion and
    fusion type.

    This is useful for further EDA and cleaning of data, as some methods are no longer
    applicable, or contain too much noise.

    Args:
        df (pd.DataFrame): Input dataframe

    Returns:
        pd.DataFrame: Dataframe with 'CHEM_METHODE_CODE mapped to three new columns:
        'DETERMINATION', 'DIGESTION' and 'FUSION'
    """
    try:
        import importlib.resources as pkg_resources
    except ImportError:
        # Try backported to PY<37 `importlib_resources`.
        import importlib_resources as pkg_resources  # noqa

    from . import data  # relative-import the *package* containing the templates

    stream = pkg_resources.open_text(data, "sarig_method_code_map.csv")
    chem_methods = pd.read_csv(stream, encoding="utf-8")

    determination_map = chem_methods.set_index("CHEM_METHOD")[
        "DETERMINATION_CODE_RD"
    ].to_dict()
    digestion_map = chem_methods.set_index("CHEM_METHOD")["DIGESTION_CODE_RD"].to_dict()
    fusion_map = chem_methods.set_index("CHEM_METHOD")["FUSION_TYPE"].to_dict()

    df["DETERMINATION"] = df.CHEM_METHOD_CODE.map(determination_map).fillna("unknown")
    df["DIGESTION"] = df.CHEM_METHOD_CODE.map(digestion_map).fillna("unknown")
    df["FUSION"] = df.CHEM_METHOD_CODE.map(fusion_map).fillna("unknown")

    return df


def export_dataset(
    df: pd.DataFrame, element: str, path: str = None, out_path: str = None
) -> None:
    """Export element dataset

    Args:
        df (pd.DataFrame): Dataframe to export
        element (str): Name of element in dataset
        path (str): Input file location
        out_path (str): File location to export to, if different from import path.
        Defaults to None
    """
    if out_path is None:
        out_path = path
    else:
        out_path = Path(out_path)

    out_file = out_path / f"{element}_processed.csv"

    df.to_csv(out_file, index=False)


def load_sarig_element_dataset(path: str, element: str) -> pd.DataFrame:
    """Load data from csv and filter to single element dataframe.
    
    Creates a 'clean' single element dataset derived from the sarig_rs_chem_exp.csv.    
    This isolates the selected element from the whole dataset and is used to create
    input data for further processing. This function uses dask to handle very large
    input datasets.

    Important note: the the sarig_rs_chem_exp.csv data is in a long format, with each
    individual analysis as a single row!

    Args:
        path (str): Path to main sarig_rs_chem_exp.csv input file.
        element (str): The element to extract and create a sub-dataset of.
        
    Returns:
        pd.DataFrame: Dataframe of single element data
    """
    path = Path(path)
    # load and filter to single element
    ddf = dd.read_csv(
        path,
        dtype={
            "ROCK_GROUP_CODE": "object",
            "ROCK_GROUP": "object",
            "LITHO_CODE": "object",
            "LITHO_CONF": "object",
            "LITHOLOGY_NAME": "object",
            "LITHO_MODIFIER": "object",
            "MAP_SYMBOL": "object",
            "STRAT_CONF": "object",
            "STRAT_NAME": "object",
            "COLLECTORS_NUMBER": "object",
            "COLLECTED_DATE": "object",
            "DH_NAME": "object",
            "OTHER_ANALYSIS_ID": "object",
            "LABORATORY": "object",
            "VALUE": "object",
            "CHEM_METHOD_CODE": "object",
            "CHEM_METHOD_DESC": "object",
        },
    )
    ddf = ddf.dropna(subset=["DRILLHOLE_NUMBER"])
    ddf = ddf[
        [
            "SAMPLE_NO",
            "SAMPLE_SOURCE_CODE",
            "DRILLHOLE_NUMBER",
            "DH_DEPTH_FROM",
            "DH_DEPTH_TO",
            "SAMPLE_ANALYSIS_NO",
            "ANALYSIS_TYPE_DESC",
            "LABORATORY",
            "CHEM_CODE",
            "VALUE",
            "UNIT",
            "CHEM_METHOD_CODE",
            "LONGITUDE_GDA2020",
            "LATITUDE_GDA2020",
        ]
    ]
    ddf = ddf[ddf.UNIT != "cps"]
    df = ddf[ddf.CHEM_CODE == element].compute()

    return df


def make_sarig_element_dataset(
    path: str, element: str, export: bool = False, out_path: str = None
) -> pd.DataFrame:
    """Create a 'clean' single element dataset derived from the sarig_rs_chem_exp.csv.
       
    This isolates the selected element from the whole dataset, converts BDL values to
    a low, non zero value, drops rows that contain other symbols such as '>' and '-' and
    converts oxides to elements and all values to ppm. It also adds chem methods to the
    dataset where possible to allow further EDA.

    This data is used to create input data for further processing. This function uses
    dask to handle very large input datasets.

    Important note: the the sarig_rs_chem_exp.csv data is in a long format, with each
    individual analysis as a single row!

    This dataset may need additional EDA and cleaning prior to further processing. In
    that case set export to True to do further processing on the returned dataset.

    Args:
        path (str): Path to main sarig_rs_chem_exp.csv input file.
        element (str): The element to extract and create a sub-dataset of.
        export (bool): Wether to export a csv version of the element dataset.
        Defaults to False.
        out_path (str, optional): Path to place out put file. Defaults to path.

    Returns:
        pd.DataFrame: Dataframe of cleaned geochemical data
    """
    df = load_sarig_element_dataset(path, element=element)

    df = clean_dataset(df)

    df = convert_oxides(df, element=element)

    df = convert_ppm(df, element=element)

    df = add_chem_method(df)

    if export:
        export_dataset(df, element=element, path=path, out_path=out_path)

    return df


if __name__ == "__main__":
    make_sarig_element_dataset()

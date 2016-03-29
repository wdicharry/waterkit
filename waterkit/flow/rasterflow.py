import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as dates
import matplotlib.ticker as ticker
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.colors import LogNorm
import matplotlib.cm
import calendar
import colormap
import usgs_data

from timeutil import get_wateryear

WATER_RIGHT_BOUNDARIES = [pd.Timestamp("2000-05-15").dayofyear, pd.Timestamp('2000-07-15').dayofyear]

CFS_DAY_TO_AF = 1.9835

def add_time_attributes(data):
    data["dayofyear"] = data.index.dayofyear
    data["year"] = data.index.year
    data["month"] = data.index.month

    data["wateryear"] = data.index.map(get_wateryear)

class GradedFlowTarget(object):
    def __init__(self, targets=[]):
        self.targets = []
        for target in targets:
            self.add(target[0], target[1])

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return other.__dict__ == self.__dict__
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(tuple(self.targets))

    def add(self, interval, value):
        start_day = pd.Timestamp("2000-" + interval[0]).dayofyear
        end_day = pd.Timestamp("2000-" + interval[1]).dayofyear

        if end_day < start_day:
            self.targets.append(((0, end_day), value))
            self.targets.append(((start_day, 366), value))
        else:
            self.targets.append(((start_day, end_day), value))
        self.targets.sort(key=lambda x: x[0][0])

    def __call__(self, day):
        for target in self.targets:
            interval = target[0]
            value = target[1]
            if interval[0] <= day and day <= interval[1]:
                return value
        return np.nan

    def __str__(self):
        return "GradedFlowTarget(" + str(self.targets) + ")"

def calculate_gap_values(data, parameter_column, target, multiplier):
    data[parameter_column] = multiplier * data[parameter_column]
    add_time_attributes(data)
    add_gap_attributes(data, parameter_column, target, multiplier)
    return data

def filter_season(data, season):
    begin = pd.Timestamp("2000-" + season[0]).dayofyear
    end = pd.Timestamp("2000-" + season[1]).dayofyear
    return data[(data.index.dayofyear > begin) & (data.index.dayofyear < end)]

def read_usgs_data(site_id, start_date, end_date,
    target=None, parameter_code=usgs_data.FLOW_PARAMETER_CODE,
    parameter_name='flow', multiplier=1.0, season=None):
    """
    Read data for the given USGS site id from start_date to
    end_date. Adds derived attributes for flow gap data.
    """
    data = usgs_data.get_gage_data(site_id, start_date, end_date,
        parameter_code=parameter_code, parameter_name=parameter_name)
    gap_data = calculate_gap_values(data, parameter_name, target, multiplier)
    if season:
        return filter_season(gap_data, season)
    else:
        return gap_data

def read_excel_data(excelfile, date_column_name, parameter_column_name,
    sheet_name=0, target_column_name=None, multiplier=1.0, season=None):
    """Read flow and optionally gap data from an Excel spreadsheet."""
    data = pd.read_excel(excelfile, sheetname=sheet_name,
        index_col=date_column_name)
    # Rename columns for consistency with other input methods.
    data.index.names = ['date']
    gap_data = calculate_gap_values(data, parameter_column_name, target_column_name, multiplier)
    if season:
        return filter_season(gap_data, season)
    else:
        return gap_data

def get_targets(target, row):
    """
    Create a dataset with e-flow targets given boundaries throughout the
    year.
    """
    current_day = pd.Timestamp(row['date']).dayofyear
    if hasattr(target, '__call__'):
        return target(current_day)
    elif isinstance(target, basestring):
        return row[target]
    else:
        return target

def add_gap_attributes(data, attribute, target, multiplier):
    """
    Add attribute target information.
    """
    if target:
        f = lambda row: get_targets(target, row)
        target_col = attribute + '-target'
        data[target_col] = multiplier * pd.Series(
            data.reset_index().apply(f, axis = 1).values, index=data.index)
        data[attribute + '-gap'] = data[attribute] - data[target_col]
    return data

def compare_sites(site_ids, start_date, end_date, attribute,
                  names=None, flow_target=None):
    datasets = map(lambda site: read_data(site, start_date, end_date, flow_target), site_ids)
    columns = map(lambda d: d[attribute], datasets)
    join = pd.concat(columns, axis=1)
    if names and len(names) == len(site_ids):
        join.columns = names
    else:
        join.columns = site_ids
    return join
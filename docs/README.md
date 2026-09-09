# duckdb-zarr

A DuckDB extension for querying Zarr-format scientific arrays with SQL.

## What It Does

**duckdb-zarr** extends DuckDB with the ability to query Zarr arrays directly using SQL. [Zarr](https://zarr.dev/) is a format for storing chunked, compressed N-dimensional arrays, widely used in scientific computing and big data applications—particularly in climate science, astronomy, genomics, and remote sensing.

With this extension, you can:

- Query Zarr array metadata (dimensions, chunk structure, data type, attributes)
- Read array data directly into DuckDB tables
- Combine Zarr data with other data sources using standard SQL joins

### The Pivot Concept

Zarr arrays are n-dimensional gridded data (like satellite imagery, climate model outputs, or sensor readings). This extension "pivots" these multi-dimensional arrays into relational tables—treating each cell in the array as a row, with coordinates as columns. This lets you use familiar SQL to query data that would otherwise require specialized array-processing tools.

### Why This Is Useful

Scientific datasets are often stored in Zarr format because it handles multi-terabyte to petabyte-scale arrays efficiently through chunking and compression. However, traditional SQL databases don't understand Zarr. This extension bridges that gap—allowing data scientists and engineers to:

- Query Zarr metadata without loading entire arrays into memory
- Perform SQL analytics on scientific data alongside structured data
- Use DuckDB's fast SQL engine to filter and aggregate chunked array data
- Integrate Zarr data pipelines with existing SQL-based workflows

This project is related to [xarray-sql](https://github.com/alxmrs/xarray-sql) and [zarr-datafusion](https://github.com/alxmrs/zarr-datafusion), which provide similar functionality for other query engines.

## Quick Start

### Installation

**Pre-built binaries**: not published yet.

**Build from source** (see Development Setup below)

### Basic Usage

```sql
-- Load the extension
LOAD 'zarr';

-- Read metadata from a Zarr store (a local path or a URL)
SELECT * FROM read_zarr_metadata('test/fixtures/xarray_tutorial/float_baseline.zarr');

-- Read a store as a table
SELECT * FROM read_zarr('test/fixtures/xarray_tutorial/float_baseline.zarr');

-- Filter with plain SQL on the coordinate columns
SELECT time, lat, lon, temperature
FROM read_zarr('test/fixtures/xarray_tutorial/float_baseline.zarr')
WHERE lat > 0 AND lon < 180;

-- A CF-encoded time coordinate ("<step> since <reference>" in its units attr)
-- becomes a TIMESTAMP, so date predicates and date functions just work.
SELECT date_trunc('month', time) AS month, AVG(air) AS mean_air
FROM read_zarr('test/fixtures/xarray_tutorial/air_temperature.zarr')
WHERE time BETWEEN TIMESTAMP '2014-06-01' AND TIMESTAMP '2014-09-01'
GROUP BY month ORDER BY month;

-- decode_times=false gives back the raw on-disk offsets instead.
-- Columns on the artificial CF calendars (noleap, 360_day, julian) are always
-- left raw, since those years have no wall-clock equivalent.
SELECT time FROM read_zarr('test/fixtures/xarray_tutorial/air_temperature.zarr',
                           decode_times=false) LIMIT 1;
```

For a small bioimage walkthrough, see [Querying OME-Zarr](ome-zarr.md).
For the domains covered by the current test suite, see
[Tested scientific domains](domains.md).

### OME-Zarr Features

OME-Zarr stores often contain nested arrays for resolution levels and labels.
Use metadata discovery first to see the available store-relative paths:

```sql
SELECT name, dims, shape, dtype
FROM read_zarr_metadata('test/fixtures/bioimage/ome_zarr/synthetic_multichannel.ome.zarr');
```

Then pass `array_path=` when you want a specific image or label array:

```sql
SELECT c, AVG(value) AS mean_intensity
FROM read_zarr('test/fixtures/bioimage/ome_zarr/synthetic_multichannel.ome.zarr', array_path='0')
GROUP BY c;

SELECT value AS label, COUNT(*) AS pixels
FROM read_zarr('test/fixtures/bioimage/ome_zarr/synthetic_multichannel.ome.zarr', array_path='labels/nuclei/0')
WHERE value > 0
GROUP BY label;
```

`array_path` is optional for simple stores where the reader can infer a single
compatible array group. It becomes useful for multiscale images, nested labels,
or stores with multiple incompatible array shapes.

## Development Setup

```shell
make configure
make debug
duckdb -unsigned # run the extension
make test_debug # testing
make test_release # testing the release build
```

### Related Projects

- [xarray-sql](https://github.com/alxmrs/xarray-sql) — xarray integration for DuckDB
- [zarr-datafusion](https://github.com/alxmrs/zarr-datafusion) — Zarr support for DataFusion
- [DuckDB](https://github.com/duckdb/duckdb) — In-process SQL OLAP database

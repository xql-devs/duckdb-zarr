"""
Real-data HTTP integration tests.

These read an *actual public* Zarr **v2** store over HTTPS — the exact scenario
the `.zmetadata` remote fix targets — so they validate the work end-to-end
against real-world data the synthetic loopback fixtures can't capture: a real
consolidated `.zmetadata`, blosc compression, CF bounds variables, and large
chunked arrays.

They hit the network, so they are marked `network` and skip automatically when
the store is unreachable (offline / CI without egress).

Run with:
    make test_http_real
    # or directly:
    pytest test/test_http_integration_real.py \
        --extension build/debug/zarr.duckdb_extension
"""
import urllib.request

import duckdb
import pytest

# Pangeo GPCP daily precipitation: Zarr v2 + consolidated `.zmetadata`,
# blosc-compressed, with CF bounds variables (lat_bounds/lon_bounds/time_bounds)
# that make it a multi-group store — a realistic public target for the reader.
GPCP = "https://ncsa.osn.xsede.org/Pangeo/pangeo-forge/gpcp-feedstock/gpcp.zarr"
PRECIP_DIMS = "['time','latitude','longitude']"

pytestmark = pytest.mark.network


@pytest.fixture(scope="module")
def con(extension_path):
    """DuckDB connection with the zarr extension loaded."""
    c = duckdb.connect(config={"allow_unsigned_extensions": True})
    c.execute(f"LOAD '{extension_path}'")
    return c


@pytest.fixture(scope="module")
def gpcp():
    """Skip the whole module when the public store is unreachable."""
    try:
        with urllib.request.urlopen(f"{GPCP}/.zmetadata", timeout=20) as resp:
            if resp.status != 200:
                pytest.skip(f"GPCP store returned HTTP {resp.status}")
    except Exception as exc:  # DNS/timeout/connection/HTTP error → offline
        pytest.skip(f"GPCP store unreachable: {exc}")
    return GPCP


def test_metadata_enumerates_v2_arrays(con, gpcp):
    """read_zarr_metadata enumerates arrays from the remote v2 `.zmetadata`.

    This is the crux of the fix: without `.zmetadata` support the reader can't
    list any arrays in a remote v2 store and the query errors at bind.
    """
    roles = dict(
        con.execute(f"SELECT name, role FROM read_zarr_metadata('{gpcp}')").fetchall()
    )
    assert roles.get("precip") == "data"
    assert roles.get("latitude") == "coord"
    assert roles.get("longitude") == "coord"
    assert roles.get("time") == "coord"


def test_coordinate_pivot(con, gpcp):
    """The coordinate pivot works over HTTP (projection skips the precip chunk)."""
    row = con.execute(
        "SELECT MIN(latitude), COUNT(*) FROM ("
        f"  SELECT latitude FROM read_zarr('{gpcp}', dims={PRECIP_DIMS}) LIMIT 500"
        ")"
    ).fetchone()
    assert row[0] == -90.0  # GPCP latitude starts at the south pole
    assert row[1] == 500


def test_precip_decode(con, gpcp):
    """End-to-end decode of a real blosc-compressed v2 chunk fetched over HTTP."""
    total, non_null = con.execute(
        "SELECT COUNT(*), COUNT(precip) FROM ("
        f"  SELECT precip FROM read_zarr('{gpcp}', dims={PRECIP_DIMS}) LIMIT 200"
        ")"
    ).fetchone()
    assert total == 200
    assert non_null >= 1  # at least some real precip values decoded (rest may be fill/NULL)


# ── Real public OME-Zarr (IDR) via array_path ───────────────────────────────
# A real bioimage store with NO consolidated metadata and NO per-array dimension
# metadata — exactly the case array_path (open the array without listing the
# store) plus OME multiscales.axes dimension names unlock.
IDR_OME = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr"


@pytest.fixture(scope="module")
def idr():
    """Skip when the IDR OME-Zarr store is unreachable."""
    try:
        with urllib.request.urlopen(f"{IDR_OME}/0/.zarray", timeout=20) as resp:
            if resp.status != 200:
                pytest.skip(f"IDR store returned HTTP {resp.status}")
    except Exception as exc:
        pytest.skip(f"IDR store unreachable: {exc}")
    return IDR_OME


def test_idr_ome_zarr_array_path(con, idr):
    """A real OME-Zarr image with no consolidated metadata reads by array_path;
    the c/z/y/x dimensions are recovered from OME multiscales.axes."""
    rows = con.execute(
        f"SELECT c, z, y, x, value FROM read_zarr('{idr}', array_path='0') LIMIT 100"
    ).fetchall()
    assert len(rows) == 100
    assert all(r[0] == 0 and r[1] == 0 for r in rows)  # first chunk: channel 0, z 0
    assert all(r[4] is not None for r in rows)          # uint16 intensities decoded

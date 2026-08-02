use std::collections::HashMap;

use zarrs::storage::{
    byte_range::ByteRangeIterator, Bytes, MaybeBytesIterator, ReadableStorageTraits, StorageError,
    StoreKey,
};

use super::meta::ZarrStore;

/// Wraps a remote store with an in-memory cache of its consolidated metadata.
///
/// `Array::open` issues up to three GETs per array (a v3 `zarr.json` probe,
/// then `.zarray`, then `.zattrs`), and dim-group inference in `meta.rs` opens
/// every array in the store several times over while classifying coords,
/// bounds vars, and dim groups. For a store with O(100) arrays — common for
/// CF-convention ocean/atmosphere datasets that split each 3-D variable into
/// one 2-D array per depth level — that is thousands of HTTP round trips
/// before a single byte of chunk data is read. Since consolidated metadata
/// (`.zmetadata` for v2, `consolidated_metadata` in `zarr.json` for v3)
/// already contains every array's metadata document, serving those lookups
/// from memory turns O(arrays) round trips into O(1).
pub struct ConsolidatedCacheStore {
    inner: ZarrStore,
    cache: HashMap<StoreKey, Bytes>,
}

impl ConsolidatedCacheStore {
    pub fn new(inner: ZarrStore, cache: HashMap<StoreKey, Bytes>) -> Self {
        Self { inner, cache }
    }
}

/// Whether `key` names a Zarr metadata document (as opposed to chunk data).
///
/// Consolidated metadata is authoritative over every metadata document in the
/// hierarchy — that is the entire premise of using it to enumerate a remote
/// store instead of listing directories (object stores can't list). So a
/// metadata key that isn't in the cache is not just uncached, it is *absent*:
/// e.g. `Array::open`'s v3 `{name}/zarr.json` probe against a v2-only store
/// (consolidated via `.zmetadata`) can be answered `None` from memory rather
/// than costing a real 404 round trip for every array opened.
fn is_metadata_key(key: &StoreKey) -> bool {
    let s = key.as_str();
    for suffix in ["zarr.json", ".zarray", ".zattrs", ".zgroup"] {
        if s == suffix || s.ends_with(&format!("/{suffix}")) {
            return true;
        }
    }
    false
}

impl ReadableStorageTraits for ConsolidatedCacheStore {
    fn get_partial_many<'a>(
        &'a self,
        key: &StoreKey,
        byte_ranges: ByteRangeIterator<'a>,
    ) -> Result<MaybeBytesIterator<'a>, StorageError> {
        if let Some(data) = self.cache.get(key) {
            let data = data.clone();
            let out = Box::new(byte_ranges.map(move |byte_range| {
                let size = data.len() as u64;
                let start = byte_range.start(size) as usize;
                let end = byte_range.end(size) as usize;
                Ok(data.slice(start..end))
            }));
            return Ok(Some(out));
        }
        if is_metadata_key(key) {
            return Ok(None);
        }
        self.inner.get_partial_many(key, byte_ranges)
    }

    fn size_key(&self, key: &StoreKey) -> Result<Option<u64>, StorageError> {
        if let Some(data) = self.cache.get(key) {
            return Ok(Some(data.len() as u64));
        }
        if is_metadata_key(key) {
            return Ok(None);
        }
        self.inner.size_key(key)
    }

    fn supports_get_partial(&self) -> bool {
        self.inner.supports_get_partial()
    }
}

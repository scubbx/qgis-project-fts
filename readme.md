# Project Full-Text-Search

This QGIS-plugin adds full-text-search capability to all datasets currently loaded in a QGIS project.

## How it works

When initialized, the plugin creates a folder at the same location as the projects file name. For each layer, an SQLite database containing all attributes of one layer is indexed with a trigram-index enabling a fault-tolerant and fast full-text search.
This multi-database approach (in contrast to a single-database one) is used to enable concurrent indexing and to avoid conflicts with multiple open connections on one single database file.

When new layers are added while the plugin is active, these layers are added to the search index.

When layers are removed while the plugin is active, these layers are also removed from the search index.

**todo:** When entries are added or removed from existing layers, only these entries are also updated in the search-index.

**todo:** Possibility to turn off tracking of changes

**todo:** Visualization of number of layers/features currently in the index

**todo:** Button to clear search field

<a href="https://www.rise-world.com"><img src="RISE-logo.svg" height="250"></a>

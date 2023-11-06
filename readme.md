# Project Full-Text-Search

This QGIS-plugin adds full-text-search capability to all datasets currently loaded in a QGIS project.

## How it works

When initialized, the plugin creates a SQLite database at the same location as the projects file name. Then all attributes of all layers are indexed with a trigram-index enabling a fault-tolerant and fast full-text search.

When new layers are added while the plugin is active, these layers are added to the search index.

**todo:** When layers are removed while the plugin is active, these layers are also removed from the search index.

**todo:** When entries are added or removed from existing layers, only these entries are also updated in the search-index.

<a href="https://www.rise-world.com"><img src="RISE-logo.svg" height="250"></a>

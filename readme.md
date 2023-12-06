# Project Full-Text-Search

This QGIS-plugin adds full-text-search capability to all datasets currently loaded in a QGIS project.

## How it works

When initialized, the plugin creates a folder at the same location as the projects file name. For each layer, an SQLite database containing all attributes of one layer is indexed with a trigram-index enabling a fault-tolerant and fast full-text search.
This multi-database approach (in contrast to a single-database one) is used to enable concurrent indexing and to avoid conflicts with multiple open connections on one single database file.

When new layers are added while the plugin is active, these layers are added to the search index.

When layers are removed while the plugin is active, these layers are also removed from the search index.

The indexing mechanism is using a batch insert with a batch size of 10.000 objects.

**todo:** When entries are added or removed from existing layers, only these entries are also updated in the search-index.

**todo:** Possibility to turn off tracking of changes

<a href="https://www.rise-world.com"><img src="RISE-logo.svg" height="250"></a>

# Changelog

## v0.2

* use systems temp folder [#6](/../../issues/6)

## v0.1

* first release
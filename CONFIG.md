# Config

## Config File

A JSON formatted config file can be used to store the location of the Foundry user data directory, as well as command presets. It is possible to see the config file default location and to open the config file in the default editor using `fwt --edit`. It is also possible to manually set the config file path using `fwt --config=` option. A config file must exist in order to be loaded. If an empty config file is detected it will be populated with the default configuration. To create a new file with the default configuration use the `--mkconfig` flag. When the --mkconfig flag is present, file exists, and isn't empty it will be left as is and a warning will be logged.

- Create a default config file in the default path

```console
fwt --mkconfig
```

- Create a default config file in a specific path

```console
fwt --mkconfig --config=~/fwt.json
```

### Example

```json
{
  "dataDir": "/fvtt/Data",
  "presets": {
    "fixr20": {
      "command": "renameall",
      "description": "Rename files. Remove non alpha characters and convert to lower case",
      "lower": true,
      "remove": ["^[0-9]{3}_-_"],
      "replace": ["/_-_/_/", "/^_//", "/^\\./_./", "/_+/-/"]
    },
    "imgDedup": {
      "bycontent": true,
      "command": "dedup",
      "description": "Find duplicate image files and chooses files from the characters,journal,scenes directories to keep",
      "ext": [".png", ".jpg", ".jpeg", ".gif", ".webp"],
      "preferred": [
        "<project_dir>/characters.*token.*",
        "<project_dir>/characters",
        "<project_dir>/journal",
        "<project_dir>/scenes/backgrounds",
        "<project_dir>/scenes"
      ]
    },
    "replacePng": {
      "command": "dedup",
      "description": "looks for png files that share the same name with webp files and only keeps the webp files",
      "detect_dup_byname": true,
      "file_extensions": [".png", ".webp"],
      "preferred_patterns": [".*webp"]
    }
  }
}
```

## Presets

FWT supports storing presets for commands which allow consistent application of options across multiple uses and prevent the need to type long commands repeatedly. FWT ships with some default presets setup in the config file.

- `fwt --preset=imgDedup dedup "myadventure"`
- `fwt --config=~/fwt.json --preset=fixr20 renameall "worlds/myadventure"`

<!-- github-only -->

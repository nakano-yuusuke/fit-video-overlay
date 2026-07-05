# FIT Video Overlay

English | [日本語](#日本語)

Render FIT activity data, GPX routes, OpenStreetMap maps, graphs, and OSM-derived features as overlays on videos and still images.

## Features

- Config-driven overlay layout for MP4 videos and JPEG/PNG still images.
- Numeric overlays from any numeric FIT-derived column.
- Graph overlays from FIT columns or preprocessed feature columns.
- OpenStreetMap overlays for current-position views and full-route overview views.
- Optional GPX-based route features, such as route progress, route margin, and route-aligned OSM feature counts.
- Boundary-based place-name lookup from a local OSM `.osm.pbf` extract.
- Cached OSM tiles, Overpass feature responses, and local OSM feature indexes for repeatable processing.
- Pillow-based text rendering with optional TrueType fonts.

## Requirements

- Linux or WSL2 runtime. The video pipeline uses POSIX FIFOs and `fork`-based multiprocessing for overlay generation and copy-on-write memory sharing. Native Windows is not supported for parallel processing.
- Python 3.11+
- FFmpeg and FFprobe
- Python packages listed in `requirements.txt`

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Cartopy may require additional system libraries depending on your OS. If pip installation fails, install Cartopy via conda or your system package manager.

## Usage

Copy the example config and edit paths for your environment:

```bash
cp overlay_config.example.json overlay_config.json
```

Run:

```bash
python fit2mp4.py --config overlay_config.json
```

Generate a quick layout preview without reading FIT data, rendering real maps, or
encoding video:

```bash
python fit2mp4.py --config overlay_config.json --preview-layout
```

By default, the preview is written to
`input.output_dir/overlay_layout_preview.png`. Use `--preview-output` to choose a
different path.

You can also run without JSON to use the built-in default layout:

```bash
python fit2mp4.py /path/to/media_dir /path/to/activity.fit /path/to/output_dir
```

## Configuration Notes

- `overlay_config.json` is intentionally ignored by Git because it usually contains local paths.
- Use `overlay_config.example.json` as the public template.
- `cache/tiles` stores OSM raster tiles.
- `cache/osm_features` stores Overpass responses and local OSM-derived indexes such as traffic-signal positions and place-name boundaries.
- `.fit`, `.gpx`, video files, and still images are ignored by default because they are often large or private.

## Configuration Reference

Top-level sections:

| Key | Description |
| --- | --- |
| `input.mp4_dir` | Directory containing source MP4, JPEG, and PNG files. |
| `input.fit_path` | FIT activity file used as the data source. |
| `input.output_dir` | Directory where generated overlays and final media are written. |
| `processing.default_refresh_rate_hz` | Default overlay refresh rate when an overlay does not specify one. |
| `processing.fit_time_offset_seconds` | Time offset applied to FIT timestamps for camera synchronization. |
| `processing.media_time_offsets` | Optional stepped offsets applied to video metadata times. Each item has `from` and `offset_seconds`; still image inputs are not affected. |
| `processing.max_fit_duration_minutes` | Optional maximum FIT duration to load; `null` loads the full FIT. |
| `processing.max_parallel_videos` | Maximum number of videos processed concurrently. Parallel video processing requires Linux or WSL2. |
| `still_exports` | Optional still-frame exports from videos. Set `enabled`, `positions`, and/or `interval_seconds`. |
| `layout.reference_resolution` | Reference media size for overlay layout coordinates, e.g. `[3840, 2160]`. |
| `layout.scale_mode` | Layout scaling mode. `fit` scales overlays uniformly to each input media file's resolution. |
| `encoding.codec` | FFmpeg video codec for the final output. |
| `encoding.cq` | Constant quality value for codecs that use CQ, such as NVENC. |
| `encoding.crf` | Constant rate factor for codecs that use CRF, such as x264/x265. |
| `encoding.preset` | FFmpeg encoder preset. |
| `encoding.pixel_format` | Output pixel format, usually `yuv420p`. |
| `encoding.copy_audio` | Whether to copy audio from the input video. |
| `encoding.output_mode` | `composited` writes source media with overlays burned in; videos become `<stem>_output.mp4` and still images become `<stem>_output.jpg` or `.png`. `transparent_overlay` writes overlays only; videos become alpha-channel QuickTime Animation `<stem>_overlay.mov` and still images become alpha-channel `<stem>_overlay.png`. |
| `encoding.ffmpeg_binary` | Path to the FFmpeg executable. |
| `encoding.ffprobe_binary` | Path to the FFprobe executable. |
| `encoding.noautorotate` | Pass `-noautorotate` to FFmpeg/FFprobe inputs when true. Useful when action-camera rotation metadata should be ignored. |
| `styles.background` | Default overlay background style. Overlays can override it with their own `background`. |
| `styles.text` | Default text style inherited by text-based overlays. |

When `layout` is set, overlays are rendered at the reference size and each completed overlay layer is scaled during FFmpeg composition. If `layout` is omitted, overlay coordinates and sizes are used as fixed pixels for backward compatibility.

Still images use EXIF `DateTimeOriginal`, `DateTimeDigitized`, or `DateTime` as the shot time. EXIF offset tags are honored when present; otherwise EXIF timestamps are interpreted in the application display timezone. If no EXIF timestamp is available, the file modification time is used.

`processing.media_time_offsets` applies stepped corrections to video metadata
times before looking up FIT data. `from` is a source MP4 file name in
`input.mp4_dir`; its `creation_time` becomes the start of that correction. The
same offset applies to later videos until another rule starts. Positive values
make the overlay use later FIT data; negative values use earlier FIT data.

```json
"media_time_offsets": [
  {
    "from": "DJI_20260607095018_0490_D.MP4",
    "offset_seconds": 60.5
  },
  {
    "from": "DJI_20260608123456_0530_D.MP4",
    "offset_seconds": 0.0
  }
]
```

Background style object:

| Key | Description |
| --- | --- |
| `type` | `solid` or `image`. |
| `path` | Image path. Required when `type` is `image`. |
| `color` | RGB solid background color, e.g. `[32, 32, 32]`. |
| `alpha` | Background opacity from `0.0` to `1.0`. Values below `1.0` generate an alpha-capable ProRes 4444 `.mov` overlay. |

Common overlay keys:

| Key | Description |
| --- | --- |
| `id` | Unique overlay identifier. Used in generated file names. |
| `type` | Overlay type: `time`, `metric`, `text`, `graph`, or `map`. |
| `enabled` | Whether this overlay is generated. |
| `x`, `y` | Overlay position in pixels on `layout.reference_resolution`; scaled for each input media file. |
| `width`, `height` | Overlay size in pixels on `layout.reference_resolution`; scaled for each input media file. Values must be even for video encoding. |
| `refresh_rate_hz` | Overlay video frame rate. Still images use only the frame for the image shot time. |
| `background` | Optional background override. Uses the same object format as `styles.background`. |

Shared text style keys:

| Key | Description |
| --- | --- |
| `position` | Text position in pixels. |
| `font_scale` | Legacy OpenCV-style scale; used only when `font_size` is omitted. |
| `font_size` | Pillow font size in pixels. |
| `font_path` | Optional path to a TrueType/OpenType font file. |
| `color` | RGB text color, e.g. `[255, 255, 255]`. |
| `thickness` | Text stroke thickness. |

`time` overlay:

| Key | Description |
| --- | --- |
| `background` | Optional background override. Use `{"type": "image", "path": "time_background.png"}` for an image background. |
| `timezone` | Display timezone, such as `Asia/Tokyo`. |
| `time_format` | `strftime` format string. |
| `text` | Text style object. |

`metric` overlay:

| Key | Description |
| --- | --- |
| `background` | Optional background override. Omit it to inherit `styles.background`. |
| `column` | Numeric DataFrame column to display. |
| `multiplier` | Value multiplier for unit conversion. |
| `value_format` | Python format string using `{value}`. `duration_margin` formats seconds as `+HH:MM` or `-HH:MM`; `{duration_margin}` embeds that formatted value inside a larger label. |
| `empty_text` | Text shown when no value is available. |
| `interpolation` | `linear` or `previous`. |
| `max_interpolation_gap_seconds` | Maximum gap allowed for linear interpolation. |
| `positive_color`, `negative_color` | Optional value colors used when both are set. |
| `text` | Text style object. |

`text` overlay:

| Key | Description |
| --- | --- |
| `background` | Optional background override. Omit it to inherit `styles.background`. |
| `column` | Text DataFrame column to display. |
| `empty_text` | Text shown when no value is available. |
| `text` | Text style object. |

`graph` overlay:

| Key | Description |
| --- | --- |
| `engine` | `opencv` or `matplotlib_strip`. |
| `style_path` | Optional `.mplstyle` file for matplotlib graphs. |
| `plot_type` | Currently `line`. |
| `line_draw_style` | `auto`, `linear`, or `steps-post`. |
| `column` | Numeric DataFrame column to graph. |
| `multiplier` | Y-value multiplier for unit conversion. |
| `value_format` | Current-value format string using `{value}`. |
| `viewport_mode` | `follow` for sliding window, or `overview` for full FIT range. |
| `follow_anchor_ratio` | Current-position ratio in `follow` mode. `1.0` is right edge, `0.5` is center. |
| `window_seconds` | Display width in seconds for `follow` mode. |
| `x_column` | Optional numeric column for the X axis, such as `distance` or `route_progress_m`. |
| `x_multiplier` | X-value multiplier for unit conversion. |
| `x_value_format` | X-axis label format string using `{value}`. |
| `y_min`, `y_max` | Optional fixed Y-axis bounds. |
| `interpolation` | Sampling method: `linear` or `previous`. |
| `max_interpolation_gap_seconds` | Maximum gap allowed for linear interpolation. |
| `sample_interval_seconds` | Optional graph sampling interval. Useful for `previous` sampling. |
| `background` | Optional graph background override. Omit it to inherit `styles.background`. |
| `plot_background_color` | RGB plot-area background color. |
| `grid_color`, `axis_color`, `line_color`, `text_color` | Colors for OpenCV graph rendering and fallback elements. |
| `line_thickness` | Graph line thickness. |
| `padding` | Plot padding `[left, top, right, bottom]`. |
| `strip_pixels_per_second` | Optional pixel density for `matplotlib_strip` follow mode. |
| `matplotlib_dpi` | DPI used for matplotlib rendering. |
| `show_axes` | Whether to render matplotlib axes. |
| `axes_layer_order` | `front` or `behind`. |
| `show_x_axis_labels` | Whether to show X-axis tick labels. |
| `show_current_marker` | Whether to draw the current-position vertical marker. |
| `current_marker_color`, `current_marker_thickness`, `current_marker_radius` | Current marker style. |
| `show_value` | Whether to display the current numeric value. |
| `value_text` | Text style object for the current value. |
| `show_poi` | Draw shared points of interest on `matplotlib_strip` graphs. POIs are anchored by GPX route progress and can be mapped to elapsed time, `distance`, or `route_progress_m` X axes. |
| `poi_icon_size` | Optional overlay-specific POI PNG size `[width, height]`. Overrides `points_of_interest` icon sizes. |
| `poi_match_threshold_m` | Maximum nearest FIT-to-POI route-progress distance used when mapping POIs to elapsed time or another X column. Defaults to `300`. |
| `poi_text` | Text style object for POI labels. |
| `empty_text` | Text shown when no value is available. |

`map` overlay:

| Key | Description |
| --- | --- |
| `background` | Optional map background alpha override, e.g. `{"alpha": 0.65}`. Route, track, POIs, and current-position markers stay opaque. |
| `viewport_mode` | `follow` or `route_overview`. |
| `display_size_m` | Follow-mode map scale. |
| `track_margin_m` | Extra margin around the route for overview maps. |
| `gpx_path` | Optional GPX route path. Required when `show_route` is true. |
| `show_route` | Draw the planned GPX route. |
| `show_track` | Draw the traveled FIT track up to the current time. |
| `route_color`, `track_color` | RGB line colors. |
| `route_thickness`, `track_thickness` | Route and track line thickness. |
| `cache_dir` | OSM tile cache directory. |
| `icon`, `icon_size`, `directional_icons` | Current-position icon settings. |
| `use_icon` | Use icon marker when true; circle marker when false. |
| `circle_radius` | Circle marker radius. |
| `tile_zoom` | OSM tile zoom level. |
| `direction_window_radius` | Number of surrounding FIT points used for direction smoothing. |
| `direction_change_confirmations` | Consecutive direction detections required before switching icon direction. |
| `direction_min_distance_m` | Minimum movement distance used for direction calculation. |
| `show_poi` | Draw shared points of interest on the map. |
| `poi_icon_size` | Optional overlay-specific POI PNG size `[width, height]`. Overrides `points_of_interest` icon sizes. |
| `poi_text` | Text style object for POI labels. |
| `debug` | Print map debug information. |

`features.grade`:

| Key | Description |
| --- | --- |
| `enabled` | Enable grade preprocessing. |
| `ride` | Grade calculated from FIT ride distance and altitude. |
| `route` | Grade calculated from GPX route progress and route altitude. |

Each `ride` / `route` object accepts:

| Key | Description |
| --- | --- |
| `enabled` | Enable this grade series. |
| `distance_column` | Distance/progress column used for the X axis. Defaults to `distance` for `ride`, `route_progress_m` for `route`. |
| `altitude_column` | Altitude column. Defaults to `altitude` for `ride`, `route_altitude_m` for `route`. |
| `column` | Generated grade column. Defaults to `grade_percent` for `ride`, `route_grade_percent` for `route`. |
| `window_m` | Distance window used to smooth grade calculation. Defaults to `200`. |

Route grade requires `features.route_progress.enabled: true` and
`features.route_progress.add_route_altitude: true`.

Grade can be displayed with a normal `metric` overlay:

```json
{
  "type": "metric",
  "column": "route_grade_percent",
  "value_format": "Route {value:+.1f}%",
  "empty_text": "--.-%"
}
```

`features.route_margin`:

| Key | Description |
| --- | --- |
| `enabled` | Enable route-margin preprocessing. |
| `gpx_path` | Planned route GPX path. |
| `target_speed_kmh` | Assumed target speed used to estimate arrival time. |
| `deadline_time` | Goal deadline in `YYYY-MM-DD HH:MM` local time (e.g. `"2026-05-12 21:30"`). Legacy `HH:MM` format is also accepted (inferred from the activity start date, rolling over to the next day if already past). |
| `timezone` | Timezone used for the deadline. |
| `off_route_threshold_m` | Maximum distance from GPX route before the point is treated as off route. |
| `search_ahead_m`, `search_behind_m` | Route matching search window. |
| `progress_column` | Route progress column to reuse or generate. Defaults to `route_progress_m`. |
| `column` | Name of the generated route-margin column. Defaults to `route_margin_seconds`. |

`search_ahead_m` and `search_behind_m` constrain route matching around the
previous matched GPX progress. For example, if the previous match was at
120.0 km and the settings are `search_ahead_m: 5000` and
`search_behind_m: 300`, the next FIT point is matched only between 119.7 km
and 125.0 km on the GPX route. This avoids jumping to a nearby but unrelated
part of a route at intersections, loops, and out-and-back sections.

Increase `search_ahead_m` when progress does not recover after GPS gaps or
long video gaps. Decrease it when matching jumps forward to a later nearby
section. Increase `search_behind_m` when real backtracking or detours should be
followed. Decrease it when matching is pulled back to an earlier nearby
section. These settings affect GPX route-progress matching only; they do not
change map zoom or visible map area.

Route margin is displayed with a normal `metric` overlay that references the generated column:

```json
{
  "id": "route_margin",
  "type": "metric",
  "column": "route_margin_seconds",
  "value_format": "Margin {duration_margin}",
  "positive_color": [80, 255, 80],
  "negative_color": [255, 80, 80]
}
```

`features.route_progress`:

| Key | Description |
| --- | --- |
| `enabled` | Enable GPX route matching. |
| `gpx_path` | Planned route GPX path. |
| `add_route_altitude` | Add `route_altitude_m` from GPX `<ele>` values. |
| `off_route_threshold_m` | Maximum distance from the GPX route before the point is treated as off route. |
| `search_ahead_m`, `search_behind_m` | Route matching search window. |
| `progress_column` | Name of the generated route progress column. Defaults to `route_progress_m`. |
| `altitude_column` | Name of the generated GPX altitude column. Defaults to `route_altitude_m`. |

`search_ahead_m` and `search_behind_m` have the same meaning as in
`features.route_margin`: they define how far forward and backward from the
previous matched GPX progress the next FIT point may be matched.

`features.traffic_signals`:

| Key | Description |
| --- | --- |
| `enabled` | Enable traffic-signal preprocessing. |
| `route_source` | `gpx` for planned route, or `fit` for the recorded track. |
| `gpx_path` | GPX path used when `route_source` is `gpx`. |
| `cache_dir` | Overpass response cache directory. |
| `bucket_distance_m` | Distance bucket size for signal counts. |
| `signal_match_threshold_m` | Maximum signal-to-route distance. |
| `route_match_threshold_m` | Maximum FIT-to-route matching distance. |
| `bbox_margin_m` | Extra margin around route bbox for Overpass queries. |
| `overpass_url` | Overpass API endpoint. |
| `column` | Name of the generated signal-count column. |

`features.place_names`:

| Key | Description |
| --- | --- |
| `enabled` | Enable boundary-based place-name preprocessing. |
| `source` | Currently `osm_pbf`. |
| `route_source` | `gpx` for planned route, or `fit` for the recorded track. |
| `gpx_path` | GPX path used when `route_source` is `gpx`. |
| `pbf_path` | Local OSM `.osm.pbf` extract path, such as a country extract. |
| `cache_dir` | OSM feature cache directory. |
| `admin_levels` | OSM administrative boundary levels to load and concatenate in that order. For Japanese prefecture + municipality, use `[4, 7]`; for municipality only, use `[7]`. |
| `bbox_margin_m` | Extra margin around the route bbox when building a route-scoped cache. |
| `name_tags` | Ordered OSM name tags to prefer, e.g. `["name:ja", "name", "name:en"]`. |
| `column` | Name of the generated place-name column. Defaults to `place_name`. |

`points_of_interest`:

| Key | Description |
| --- | --- |
| `enabled` | Enable shared POI loading. |
| `gpx_path` | Optional default GPX path used to resolve manual POIs. |
| `sources` | External POI sources. Currently supports `{"type": "gpx_wpt"}`. |
| `items` | Manually defined POIs. Each item needs `id` and either `distance_m` or `lat`/`lon`. |

GPX WPT POIs use the WPT `<name>` as the label. Overlays draw their own POI marker at the POI position. Marker priority is `icon` PNG, then `emoji`, then a fallback white circle. Manual POIs can set `label`, `emoji`, `icon`, `icon_size`, `distance_m`, or `lat`/`lon`; emoji rendering depends on the configured font. POIs are kept separately from the FIT-derived DataFrame and are passed directly to overlays.

## Metric and Graph Columns

`metric` and `graph` overlays can use any numeric column available in the FIT-derived DataFrame.

Examples:

```json
{
  "type": "metric",
  "column": "heart_rate",
  "value_format": "{value:.0f}"
}
```

```json
{
  "type": "graph",
  "column": "power",
  "value_format": "{value:.0f} W"
}
```

Use `multiplier` for unit conversion:

- Speed from m/s to km/h: `"multiplier": 3.6`
- Distance from m to km: `"multiplier": 0.001`

Common FIT columns include `speed`, `distance`, `altitude`, `heart_rate`, `cadence`, `power`, and `temperature`. Feature columns added during preprocessing, such as `route_progress_m`, `route_altitude_m`, `route_margin_seconds`, `grade_percent`, `route_grade_percent`, and `traffic_signal_count_per_km`, can also be displayed or graphed.

Text feature columns, such as `place_name`, are displayed with a `text` overlay:

```json
{
  "type": "text",
  "column": "place_name",
  "empty_text": "-"
}
```

Graph POIs are defined by GPX route distance. When the graph X axis is elapsed time or another column such as `distance`, the renderer finds the nearest FIT row by `route_progress_m` and uses that row's timestamp or X-column value.

Use `route_progress_m` as the X axis when graph POIs should line up directly with GPX planned-route distances:

```json
{
  "type": "graph",
  "engine": "matplotlib_strip",
  "viewport_mode": "overview",
  "x_column": "route_progress_m",
  "x_multiplier": 0.001,
  "column": "traffic_signal_count_per_km",
  "show_poi": true,
  "poi_icon_size": [20, 20]
}
```

Shared POIs can be loaded from GPX waypoints and mixed with manual entries:

```json
"points_of_interest": {
  "enabled": true,
  "sources": [
    {
      "type": "gpx_wpt",
      "gpx_path": "route.gpx",
      "emoji": "📍"
    }
  ],
  "items": [
    {
      "id": "pc2",
      "label": "PC2",
      "icon": "assets/pc.png",
      "icon_size": [28, 28],
      "distance_m": 87000
    }
  ]
}
```

## Traffic Signal Graph

Traffic signal features are optional and controlled by:

```json
"features": {
  "traffic_signals": {
    "enabled": true,
    "route_source": "gpx",
    "gpx_path": "route.gpx",
    "bucket_distance_m": 1000,
    "signal_match_threshold_m": 50,
    "column": "traffic_signal_count_per_km"
  }
}
```

The implementation:

- Fetches `highway=traffic_signals` from Overpass for the route bounding box.
- Caches the result under `cache/osm_features`.
- Matches signals within `signal_match_threshold_m` of the route.
- Counts raw signal nodes per `bucket_distance_m`; no clustering is applied yet.
- Adds `traffic_signal_count_per_km` and `route_progress_m` to the overlay DataFrame.

If an overlay references `traffic_signal_count_per_km` while `features.traffic_signals.enabled` is false, config loading fails with an explicit error.

## Place Names

Place-name features are optional and controlled by `features.place_names`. They read administrative boundaries from a local OSM `.osm.pbf` file, cache the boundary index under `cache/osm_features`, and add a text column such as `place_name` to the overlay DataFrame.

```json
"features": {
  "place_names": {
    "enabled": true,
    "source": "osm_pbf",
    "route_source": "gpx",
    "gpx_path": "route.gpx",
    "pbf_path": "data/osm/japan-latest.osm.pbf",
    "admin_levels": [4, 7],
    "column": "place_name"
  }
}
```

Use a `text` overlay to display the generated column. For long routes, prebuilding the boundary cache avoids rebuilding it during video generation:

```bash
python build_place_cache.py --config overlay_config.json
```

## Sample Assets

Image assets such as `icon.png`, `icon_north.png`, `poi_pin.png`, and
`time_background.png` are intentionally not included in the public repository.
The example config references these names as placeholders. Provide your own
local PNG/JPG files, or change the config to use solid backgrounds and circle
map markers.

## Development Checks

Basic syntax/config checks:

```bash
python -m compileall -q fit_overlay fit2mp4.py build_place_cache.py
python -m json.tool overlay_config.example.json >/dev/null
```

---

# 日本語

FITの走行データ、GPX予定ルート、OpenStreetMap、グラフ、OSM由来の特徴量を動画や静止画に重ねるためのツールです。

## 機能

- JSON設定によるMP4動画・JPEG/PNG静止画向けオーバーレイレイアウト
- FIT由来DataFrameの任意の数値列を使った数値表示
- FIT列または前処理で追加した特徴量列を使ったグラフ表示
- 現在地追従表示とルート全体表示に対応したOpenStreetMapオーバーレイ
- ルート進捗、貯金時間、ルート沿いOSM特徴量集計など、GPXを使った任意のルート特徴量
- ローカルOSM `.osm.pbf` extractを使った行政境界ベースの地名表示
- OSMタイル、Overpass特徴量レスポンス、ローカルOSM特徴量インデックスのキャッシュ
- Pillowによる文字描画と任意TrueTypeフォント指定

## 必要なもの

- LinuxまたはWSL2実行環境。動画生成パイプラインはPOSIX FIFOと、`fork` ベースのマルチプロセスによるオーバーレイ生成・copy-on-writeメモリ共有を使います。Windowsネイティブ環境での並列処理は非対応です。
- Python 3.11以上
- FFmpeg / FFprobe
- `requirements.txt` に記載されたPythonパッケージ

Python依存関係のインストール:

```bash
pip install -r requirements.txt
```

CartopyはOSによって追加のシステムライブラリが必要です。pipで失敗する場合は、condaまたはOSのパッケージマネージャでCartopyを入れてください。

## 使い方

サンプル設定をコピーし、自分の環境のパスに書き換えます。

```bash
cp overlay_config.example.json overlay_config.json
```

実行:

```bash
python fit2mp4.py --config overlay_config.json
```

FITデータ読み込み、実地図描画、動画エンコードをせず、配置確認用の軽量プレビューを
生成できます。

```bash
python fit2mp4.py --config overlay_config.json --preview-layout
```

デフォルトでは `input.output_dir/overlay_layout_preview.png` に出力します。
出力先を変える場合は `--preview-output` を指定します。

JSONを使わず、組み込みのデフォルトレイアウトで実行することもできます。

```bash
python fit2mp4.py /path/to/media_dir /path/to/activity.fit /path/to/output_dir
```

## 設定メモ

- `overlay_config.json` はローカルパスを含みやすいためGit管理から除外しています。
- 公開用テンプレートとして `overlay_config.example.json` を使ってください。
- `cache/tiles` にはOSM地図タイルが保存されます。
- `cache/osm_features` にはOverpassから取得した信号位置や、ローカルOSM由来の地名境界インデックスなどが保存されます。
- `.fit`, `.gpx`, 動画・静止画ファイルは大きい/個人情報を含みやすいため、デフォルトで除外しています。

## 設定リファレンス

トップレベル設定:

| キー | 説明 |
| --- | --- |
| `input.mp4_dir` | 入力MP4、JPEG、PNGファイルを置いたディレクトリ。 |
| `input.fit_path` | データソースにするFITファイル。 |
| `input.output_dir` | 生成したoverlayと最終メディアの出力先。 |
| `processing.default_refresh_rate_hz` | overlayごとの指定がない場合のデフォルト更新レート。 |
| `processing.fit_time_offset_seconds` | カメラ同期用にFIT時刻へ加える補正秒数。 |
| `processing.media_time_offsets` | 動画メタデータ時刻へ段階的に加える補正。各項目は `from` と `offset_seconds` を持ちます。静止画入力には適用されません。 |
| `processing.max_fit_duration_minutes` | 読み込むFITの最大時間。`null` なら全体を読み込みます。 |
| `processing.max_parallel_videos` | 同時に処理する動画数の上限。並列動画処理にはLinuxまたはWSL2が必要です。 |
| `still_exports` | 動画からの静止画書き出し設定。`enabled`, `positions`, `interval_seconds` を指定できます。 |
| `layout.reference_resolution` | overlay配置の基準にするメディアサイズ。例: `[3840, 2160]`。 |
| `layout.scale_mode` | 配置のスケール方式。`fit` は入力メディアの解像度に合わせてoverlayを等倍率で拡大縮小します。 |
| `encoding.codec` | 最終出力に使うFFmpeg動画codec。 |
| `encoding.cq` | NVENCなどCQ系codec向けの品質値。 |
| `encoding.crf` | x264/x265などCRF系codec向けの品質値。 |
| `encoding.preset` | FFmpeg encoder preset。 |
| `encoding.pixel_format` | 出力pixel format。通常は `yuv420p`。 |
| `encoding.copy_audio` | 入力動画の音声を最終出力へコピーするか。 |
| `encoding.output_mode` | `composited` は入力メディアにoverlayを焼き込みます。動画は `<stem>_output.mp4`、静止画は `<stem>_output.jpg` または `.png` です。`transparent_overlay` はoverlayだけを出力します。動画はアルファチャンネル付きQuickTime Animationの `<stem>_overlay.mov`、静止画はアルファチャンネル付き `<stem>_overlay.png` です。 |
| `encoding.ffmpeg_binary` | FFmpeg実行ファイルのパス。 |
| `encoding.ffprobe_binary` | FFprobe実行ファイルのパス。 |
| `encoding.noautorotate` | trueの場合、FFmpeg/FFprobe入力に `-noautorotate` を渡します。アクションカメラの回転メタデータを無視したい場合に使います。 |
| `styles.background` | overlay背景のデフォルト設定。各overlayの `background` で上書きできます。 |
| `styles.text` | 文字系overlayが継承するデフォルト文字スタイル。 |

`layout` を指定した場合、overlayは基準サイズで描画され、完成したoverlayレイヤー全体をFFmpeg合成時に拡大縮小します。`layout` を省略した場合は、後方互換のため座標とサイズを固定pxとして扱います。

静止画の時刻はEXIFの `DateTimeOriginal`、`DateTimeDigitized`、`DateTime` の順に使います。EXIFの時差タグがあればそれを反映し、なければアプリケーションの表示タイムゾーンとして解釈します。EXIF時刻がない場合はファイル更新時刻を使います。

`processing.media_time_offsets` は、FITデータ参照前に動画メタデータ時刻へ
段階的な補正を加えます。`from` は `input.mp4_dir` 内のMP4ファイル名で、
その動画の `creation_time` 以降の動画に同じ補正が適用されます。次の
ルールが始まると補正値が切り替わります。正の値はより未来のFITデータを
使い、負の値はより過去のFITデータを使います。

```json
"media_time_offsets": [
  {
    "from": "DJI_20260607095018_0490_D.MP4",
    "offset_seconds": 60.5
  },
  {
    "from": "DJI_20260608123456_0530_D.MP4",
    "offset_seconds": 0.0
  }
]
```

背景スタイル設定:

| キー | 説明 |
| --- | --- |
| `type` | `solid` または `image`。 |
| `path` | 画像パス。`type` が `image` の場合に必要です。 |
| `color` | 単色背景のRGB色。例: `[32, 32, 32]`。 |
| `alpha` | 背景の不透明度。`0.0` から `1.0`。`1.0` 未満ではアルファ対応のProRes 4444 `.mov` overlayを生成します。 |

overlay共通設定:

| キー | 説明 |
| --- | --- |
| `id` | overlayの一意なID。生成ファイル名にも使われます。 |
| `type` | overlay種別。`time`, `metric`, `text`, `graph`, `map`。 |
| `enabled` | このoverlayを生成するか。 |
| `x`, `y` | `layout.reference_resolution` 上の配置位置。入力メディアごとにスケールされます。 |
| `width`, `height` | `layout.reference_resolution` 上のoverlayサイズ。入力メディアごとにスケールされます。動画エンコードのため偶数で指定します。 |
| `refresh_rate_hz` | overlay動画のフレームレート。静止画ではその時刻の1フレームだけを使います。 |
| `background` | 任意の背景上書き設定。`styles.background` と同じ形式です。 |

文字スタイル共通設定:

| キー | 説明 |
| --- | --- |
| `position` | 文字の描画位置。単位はpx。 |
| `font_scale` | 旧OpenCV風の拡大率。`font_size` 省略時の互換用です。 |
| `font_size` | Pillowで使うフォントサイズ。 |
| `font_path` | 任意のTrueType/OpenTypeフォントファイル。 |
| `color` | RGB文字色。例: `[255, 255, 255]`。 |
| `thickness` | 文字の縁取り太さ。 |

`time` overlay:

| キー | 説明 |
| --- | --- |
| `background` | 任意の背景上書き設定。画像背景なら `{"type": "image", "path": "time_background.png"}` を指定します。 |
| `timezone` | 表示タイムゾーン。例: `Asia/Tokyo`。 |
| `time_format` | `strftime` 形式の時刻フォーマット。 |
| `text` | 文字スタイル設定。 |

`metric` overlay:

| キー | 説明 |
| --- | --- |
| `background` | 任意の背景上書き設定。省略時は `styles.background` を継承します。 |
| `column` | 表示する数値DataFrame列。 |
| `multiplier` | 単位変換用の倍率。 |
| `value_format` | `{value}` を使うPython format文字列。`duration_margin` は秒数を `+HH:MM` / `-HH:MM` 形式にします。`{duration_margin}` を使うと、その表示をラベル内に埋め込めます。 |
| `empty_text` | 値がない場合に表示する文字。 |
| `interpolation` | `linear` または `previous`。 |
| `max_interpolation_gap_seconds` | 線形補間を許可する最大レコード間隔。 |
| `positive_color`, `negative_color` | 両方を指定した場合の正値/負値の文字色。 |
| `text` | 文字スタイル設定。 |

`text` overlay:

| キー | 説明 |
| --- | --- |
| `background` | 任意の背景上書き設定。省略時は `styles.background` を継承します。 |
| `column` | 表示する文字列DataFrame列。 |
| `empty_text` | 値がない場合に表示する文字。 |
| `text` | 文字スタイル設定。 |

`graph` overlay:

| キー | 説明 |
| --- | --- |
| `engine` | `opencv` または `matplotlib_strip`。 |
| `style_path` | matplotlibグラフ用の `.mplstyle` ファイル。 |
| `plot_type` | 現在は `line`。 |
| `line_draw_style` | `auto`, `linear`, `steps-post`。 |
| `column` | グラフ化する数値DataFrame列。 |
| `multiplier` | Y値の単位変換倍率。 |
| `value_format` | 現在値表示用の `{value}` format文字列。 |
| `viewport_mode` | `follow` はスライド表示、`overview` はFIT全体表示。 |
| `follow_anchor_ratio` | `follow` 時の現在位置。`1.0` は右端、`0.5` は中央。 |
| `window_seconds` | `follow` 時の表示時間幅。 |
| `x_column` | 任意のX軸列。例: `distance`, `route_progress_m`。 |
| `x_multiplier` | X値の単位変換倍率。 |
| `x_value_format` | X軸ラベル用の `{value}` format文字列。 |
| `y_min`, `y_max` | Y軸の固定範囲。省略時は自動。 |
| `interpolation` | サンプリング方法。`linear` または `previous`。 |
| `max_interpolation_gap_seconds` | 線形補間を許可する最大レコード間隔。 |
| `sample_interval_seconds` | グラフ用の再サンプリング間隔。 |
| `background` | 任意のグラフ背景上書き設定。省略時は `styles.background` を継承します。 |
| `plot_background_color` | プロット領域のRGB背景色。 |
| `grid_color`, `axis_color`, `line_color`, `text_color` | OpenCV描画やfallback要素の色。 |
| `line_thickness` | 線の太さ。 |
| `padding` | プロット余白 `[left, top, right, bottom]`。 |
| `strip_pixels_per_second` | `matplotlib_strip` のfollow表示用pixel密度。 |
| `matplotlib_dpi` | matplotlib描画DPI。 |
| `show_axes` | matplotlib軸を表示するか。 |
| `axes_layer_order` | 軸レイヤーの重ね順。`front` または `behind`。 |
| `show_x_axis_labels` | X軸ラベルを表示するか。 |
| `show_current_marker` | 現在位置の縦線・点を表示するか。 |
| `current_marker_color`, `current_marker_thickness`, `current_marker_radius` | 現在位置マーカーのスタイル。 |
| `show_value` | 現在値テキストを表示するか。 |
| `value_text` | 現在値テキストのスタイル設定。 |
| `show_poi` | `matplotlib_strip` グラフに共通POIを表示するか。POIはGPXルート進捗を基準に、経過時間、`distance`、`route_progress_m` のX軸へ変換して表示できます。 |
| `poi_icon_size` | overlayごとのPOI PNGサイズ `[width, height]`。`points_of_interest` 側のアイコンサイズを上書きします。 |
| `poi_match_threshold_m` | POIを経過時間や別のX軸列へ変換するときに許容する、FIT側ルート進捗との最大距離。デフォルトは `300`。 |
| `poi_text` | POIラベルの文字スタイル設定。 |
| `empty_text` | 値がない場合に表示する文字。 |

`map` overlay:

| キー | 説明 |
| --- | --- |
| `background` | 地図背景のアルファ上書き設定。例: `{"alpha": 0.65}`。ルート、軌跡、POI、現在地マーカーは不透明のままです。 |
| `viewport_mode` | `follow` または `route_overview`。 |
| `display_size_m` | follow表示時の地図スケール。 |
| `track_margin_m` | overview地図でルート周辺に加える余白。 |
| `gpx_path` | GPXルートパス。`show_route` がtrueの場合は必須。 |
| `show_route` | GPX予定ルートを描画するか。 |
| `show_track` | 現在時刻までのFIT軌跡を描画するか。 |
| `route_color`, `track_color` | RGB線色。 |
| `route_thickness`, `track_thickness` | ルート線・軌跡線の太さ。 |
| `cache_dir` | OSMタイルキャッシュディレクトリ。 |
| `icon`, `icon_size`, `directional_icons` | 現在地アイコン設定。 |
| `use_icon` | trueならアイコン、falseなら円マーカーを使います。 |
| `circle_radius` | 円マーカー半径。 |
| `tile_zoom` | OSMタイルzoom level。 |
| `direction_window_radius` | 方向計算に使う前後FIT点数。 |
| `direction_change_confirmations` | アイコン方向変更に必要な連続検出回数。 |
| `direction_min_distance_m` | 方向計算に使う最小移動距離。 |
| `show_poi` | 地図上に共通POIを表示するか。 |
| `poi_icon_size` | overlayごとのPOI PNGサイズ `[width, height]`。`points_of_interest` 側のアイコンサイズを上書きします。 |
| `poi_text` | POIラベルの文字スタイル設定。 |
| `debug` | 地図debug情報を出力するか。 |

`features.grade`:

| キー | 説明 |
| --- | --- |
| `enabled` | 斜度の前処理を有効にするか。 |
| `ride` | FIT実走距離と高度から計算する実走斜度。 |
| `route` | GPXルート進捗とルート高度から計算するルート斜度。 |

`ride` / `route` の各オブジェクトでは以下を指定できます。

| キー | 説明 |
| --- | --- |
| `enabled` | この斜度系列を有効にするか。 |
| `distance_column` | 距離・進捗列。`ride` のデフォルトは `distance`、`route` のデフォルトは `route_progress_m`。 |
| `altitude_column` | 高度列。`ride` のデフォルトは `altitude`、`route` のデフォルトは `route_altitude_m`。 |
| `column` | 生成する斜度列名。`ride` のデフォルトは `grade_percent`、`route` のデフォルトは `route_grade_percent`。 |
| `window_m` | 斜度計算を平滑化する距離窓。デフォルトは `200`。 |

ルート斜度には `features.route_progress.enabled: true` と
`features.route_progress.add_route_altitude: true` が必要です。

斜度は通常の `metric` overlay で表示できます。

```json
{
  "type": "metric",
  "column": "route_grade_percent",
  "value_format": "Route {value:+.1f}%",
  "empty_text": "--.-%"
}
```

`features.route_margin`:

| キー | 説明 |
| --- | --- |
| `enabled` | 貯金時間の前処理を有効にするか。 |
| `gpx_path` | 予定ルートGPXパス。 |
| `target_speed_kmh` | 到着予測に使う想定速度。 |
| `deadline_time` | ゴール制限時刻。ローカル時刻の `YYYY-MM-DD HH:MM` 形式（例： `"2026-05-12 21:30"`）。後方互換として `HH:MM` 形式も有効（開始日を基準に翻日分は自動繰り上げ）。 |
| `timezone` | 制限時刻に使うタイムゾーン。 |
| `off_route_threshold_m` | GPXルートから外れたとみなす距離。 |
| `search_ahead_m`, `search_behind_m` | ルートマッチングの探索範囲。 |
| `progress_column` | 再利用または生成するルート進捗列。デフォルトは `route_progress_m`。 |
| `column` | 生成する貯金時間列名。デフォルトは `route_margin_seconds`。 |

`search_ahead_m` と `search_behind_m` は、前回マッチしたGPX進捗距離の
周辺だけを次の探索対象にするための設定です。たとえば前回のマッチが
120.0 km地点で、`search_ahead_m: 5000`, `search_behind_m: 300` の場合、
次のFIT点はGPX上の119.7 kmから125.0 kmの範囲だけでマッチングされます。
これにより、交差、ループ、往復区間などで近くにある別区間へ飛ぶことを
抑えます。

GPS欠落後や動画間隔が長い箇所で進捗が復帰しない場合は
`search_ahead_m` を大きくします。先の近接区間へワープする場合は
小さくします。実際の戻りや寄り道を追従したい場合は
`search_behind_m` を大きくします。過去の近接区間へ吸われる場合は
小さくします。この設定はGPXルート進捗のマッチング範囲だけに効き、
地図のズームや表示範囲は変えません。

貯金時間は、生成された列を通常の `metric` overlay で参照して表示します。

```json
{
  "id": "route_margin",
  "type": "metric",
  "column": "route_margin_seconds",
  "value_format": "貯金時間 {duration_margin}",
  "positive_color": [80, 255, 80],
  "negative_color": [255, 80, 80]
}
```

`features.route_progress`:

| キー | 説明 |
| --- | --- |
| `enabled` | GPXルートマッチングを有効にするか。 |
| `gpx_path` | 予定ルートGPXパス。 |
| `add_route_altitude` | GPXの `<ele>` から `route_altitude_m` を追加するか。 |
| `off_route_threshold_m` | GPXルートから外れたとみなす距離。 |
| `search_ahead_m`, `search_behind_m` | ルートマッチングの探索範囲。 |
| `progress_column` | 生成するルート進捗列名。デフォルトは `route_progress_m`。 |
| `altitude_column` | 生成するGPX高度列名。デフォルトは `route_altitude_m`。 |

`search_ahead_m` と `search_behind_m` は `features.route_margin` と同じ意味です。
前回マッチしたGPX進捗距離から、次のFIT点を前方・後方に何mまで探すかを
指定します。

`features.traffic_signals`:

| キー | 説明 |
| --- | --- |
| `enabled` | 信号特徴量前処理を有効にするか。 |
| `route_source` | `gpx` は予定ルート、`fit` は実走軌跡。 |
| `gpx_path` | `route_source` が `gpx` の場合に使うGPXパス。 |
| `cache_dir` | Overpassレスポンスキャッシュディレクトリ。 |
| `bucket_distance_m` | 信号数を集計する距離区間。 |
| `signal_match_threshold_m` | 信号をルートに紐づける最大距離。 |
| `route_match_threshold_m` | FIT現在地をルートに紐づける最大距離。 |
| `bbox_margin_m` | Overpass問い合わせbboxに追加する余白。 |
| `overpass_url` | Overpass API endpoint。 |
| `column` | 生成する信号数列名。 |

`features.place_names`:

| キー | 説明 |
| --- | --- |
| `enabled` | 行政境界ベースの地名前処理を有効にするか。 |
| `source` | 現在は `osm_pbf`。 |
| `route_source` | `gpx` は予定ルート、`fit` は実走軌跡。 |
| `gpx_path` | `route_source` が `gpx` の場合に使うGPXパス。 |
| `pbf_path` | ローカルOSM `.osm.pbf` extractのパス。 |
| `cache_dir` | OSM特徴量キャッシュディレクトリ。 |
| `admin_levels` | 読み込んで順番に連結するOSM行政境界レベル。日本の都道府県+市町村なら `[4, 7]`、市町村のみなら `[7]`。 |
| `bbox_margin_m` | ルート範囲キャッシュ作成時にbboxへ追加する余白。 |
| `name_tags` | 優先するOSM nameタグ。例: `["name:ja", "name", "name:en"]`。 |
| `column` | 生成する地名列名。デフォルトは `place_name`。 |

`points_of_interest`:

| キー | 説明 |
| --- | --- |
| `enabled` | 共通POI読み込みを有効にするか。 |
| `gpx_path` | 手動POIの解決に使う任意のデフォルトGPXパス。 |
| `sources` | 外部POIソース。現在は `{"type": "gpx_wpt"}` に対応。 |
| `items` | 手動POI定義。各要素には `id` と、`distance_m` または `lat`/`lon` が必要です。 |

GPX WPT由来POIはWPTの `<name>` をラベルにします。overlay側でPOI位置にマーカーを描きます。マーカーは `icon` PNG、`emoji`、白丸の優先順です。手動POIでは `label`, `emoji`, `icon`, `icon_size`, `distance_m`, `lat`/`lon` を指定できますが、絵文字表示は設定フォントに依存します。POIはFIT由来DataFrameには入れず、overlayへ別データとして渡します。

## 数値表示とグラフの列指定

`metric` と `graph` は、FIT由来DataFrameに含まれる任意の数値列を指定できます。

例:

```json
{
  "type": "metric",
  "column": "heart_rate",
  "value_format": "{value:.0f}"
}
```

```json
{
  "type": "graph",
  "column": "power",
  "value_format": "{value:.0f} W"
}
```

単位変換には `multiplier` を使います。

- 速度を m/s から km/h にする: `"multiplier": 3.6`
- 距離を m から km にする: `"multiplier": 0.001`

よく使うFIT列には、`speed`, `distance`, `altitude`, `heart_rate`, `cadence`, `power`, `temperature` などがあります。前処理で追加した `route_progress_m`, `route_altitude_m`, `route_margin_seconds`, `grade_percent`, `route_grade_percent`, `traffic_signal_count_per_km` のような特徴量列も表示・グラフ化できます。

`place_name` のような文字列特徴量は `text` overlay で表示します。

```json
{
  "type": "text",
  "column": "place_name",
  "empty_text": "-"
}
```

グラフ上のPOIはGPXルート距離を基準にします。X軸が経過時間や `distance` の場合は、`route_progress_m` が最も近いFIT行を探し、その行の時刻またはX軸列の値へ変換して表示します。

POIをGPX予定ルート距離に直接合わせて表示するグラフでは、X軸に `route_progress_m` を使います。

```json
{
  "type": "graph",
  "engine": "matplotlib_strip",
  "viewport_mode": "overview",
  "x_column": "route_progress_m",
  "x_multiplier": 0.001,
  "column": "traffic_signal_count_per_km",
  "show_poi": true,
  "poi_icon_size": [20, 20]
}
```

共通POIはGPXウェイポイントと手動定義を組み合わせられます。

```json
"points_of_interest": {
  "enabled": true,
  "sources": [
    {
      "type": "gpx_wpt",
      "gpx_path": "route.gpx",
      "emoji": "📍"
    }
  ],
  "items": [
    {
      "id": "pc2",
      "label": "PC2",
      "icon": "assets/pc.png",
      "icon_size": [28, 28],
      "distance_m": 87000
    }
  ]
}
```

## 信号グラフ

信号特徴量は任意機能で、以下の設定で有効化します。

```json
"features": {
  "traffic_signals": {
    "enabled": true,
    "route_source": "gpx",
    "gpx_path": "route.gpx",
    "bucket_distance_m": 1000,
    "signal_match_threshold_m": 50,
    "column": "traffic_signal_count_per_km"
  }
}
```

処理内容:

- Overpassからルートbbox内の `highway=traffic_signals` を取得
- 結果を `cache/osm_features` にキャッシュ
- ルートから `signal_match_threshold_m` 以内の信号だけ採用
- `bucket_distance_m` ごとに信号ノード数を単純集計
- `traffic_signal_count_per_km` と `route_progress_m` をオーバーレイ用DataFrameに追加

`features.traffic_signals.enabled` が無効な状態で `traffic_signal_count_per_km` を参照するoverlayがある場合、設定読み込み時に明示的なエラーになります。

## 地名表示

地名特徴量は任意機能で、`features.place_names` で有効化します。ローカルOSM `.osm.pbf` ファイルから行政境界を読み、境界インデックスを `cache/osm_features` にキャッシュし、`place_name` などの文字列列をオーバーレイ用DataFrameに追加します。

```json
"features": {
  "place_names": {
    "enabled": true,
    "source": "osm_pbf",
    "route_source": "gpx",
    "gpx_path": "route.gpx",
    "pbf_path": "data/osm/japan-latest.osm.pbf",
    "admin_levels": [4, 7],
    "column": "place_name"
  }
}
```

生成された列は `text` overlay で表示します。長距離ルートでは、境界キャッシュを先に作っておくと動画生成時の再構築を避けられます。

```bash
python build_place_cache.py --config overlay_config.json
```

## サンプル素材

`icon.png`, `icon_north.png`, `poi_pin.png`, `time_background.png` などの
画像素材は、公開リポジトリには含めない方針です。サンプル設定ではこれらの
ファイル名をプレースホルダーとして参照しています。ローカルに自分のPNG/JPG
素材を置くか、設定を単色背景や地図の円マーカーに変更してください。

## 開発時チェック

基本的な構文・設定チェック:

```bash
python -m compileall -q fit_overlay fit2mp4.py build_place_cache.py
python -m json.tool overlay_config.example.json >/dev/null
```

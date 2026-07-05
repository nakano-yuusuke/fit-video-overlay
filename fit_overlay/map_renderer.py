"""OpenStreetMapタイルの取得と静的地図画像の生成。"""

from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path
from time import perf_counter
from urllib.request import Request, urlopen

import cartopy.io.img_tiles as cimgt
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import Image

from .map_geometry import MapGeometry


logger = logging.getLogger(__name__)


def _current_rss_mb() -> float | None:
    status_path = Path("/proc/self/status")
    try:
        for line in status_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1]) / 1024
    except OSError:
        return None
    return None


class CachedOsmTiles(cimgt.OSM):
    """OSMタイルをローカルへ保存し、同じ地図の再取得を避ける。"""

    def __init__(self, cache_dir: Path) -> None:
        super().__init__()
        self.cache_dir = cache_dir

    def get_image(self, tile):
        url = self._image_url(tile)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_name = hashlib.sha1(url.encode("utf-8")).hexdigest() + ".png"
        cache_path = self.cache_dir / cache_name

        if cache_path.exists():
            logger.debug("osm_tile_cache_hit tile=%s path=%s", tile, cache_path)
            image = Image.open(cache_path)
        else:
            logger.debug("osm_tile_cache_miss tile=%s url=%s", tile, url)
            request = Request(url, headers={"User-Agent": "fit2mp4"})
            start = perf_counter()
            with urlopen(request) as response:
                image = Image.open(io.BytesIO(response.read()))
                image.load()
            logger.debug(
                "osm_tile_downloaded tile=%s elapsed=%.2fs",
                tile,
                perf_counter() - start,
            )
            try:
                image.save(cache_path)
            except OSError:
                pass

        image = image.convert(self.desired_tile_form)
        return image, self.tileextent(tile), "lower"


class StaticMapRenderer:
    """計算済みの地図範囲を、1枚のRGB画像として描画する。"""

    def __init__(
        self,
        cache_dir: Path,
        *,
        dpi: int = 300,
        zoom: int = 18,
        max_image_pixels: int = 50_000_000,
    ) -> None:
        self.tiles = CachedOsmTiles(cache_dir)
        self.dpi = dpi
        self.zoom = zoom
        self.max_image_pixels = max_image_pixels

    def render(self, geometry: MapGeometry) -> np.ndarray:
        """OSMタイルを指定範囲・指定pixel数の静的画像へ変換する。"""
        start = perf_counter()
        image_pixels = geometry.width_px * geometry.height_px
        logger.info(
            "render_static_map started size=%dx%d zoom=%s bbox=%s rss_mb=%s",
            geometry.width_px,
            geometry.height_px,
            self.zoom,
            geometry.bbox,
            (
                f"{rss:.1f}"
                if (rss := _current_rss_mb()) is not None
                else "unknown"
            ),
        )
        if image_pixels > self.max_image_pixels:
            raise ValueError(
                "静的地図が大きすぎます: "
                f"{geometry.width_px}x{geometry.height_px}px。"
                "動画とFITの時刻差、display_size_m、地図範囲を確認してください。"
            )
        figure, axes = plt.subplots(
            figsize=(
                geometry.width_px / self.dpi,
                geometry.height_px / self.dpi,
            ),
            subplot_kw={"projection": self.tiles.crs},
            dpi=self.dpi,
            facecolor="none",
        )
        try:
            canvas = FigureCanvasAgg(figure)
            figure.subplots_adjust(0, 0, 1, 1)
            axes.spines["geo"].set_visible(False)
            axes.add_image(self.tiles, self.zoom)
            axes.set_extent(geometry.bbox)
            canvas.draw()
            rgba = np.asarray(canvas.buffer_rgba())
            image = rgba[..., :3].copy()
            logger.info(
                "render_static_map finished in %.2fs size=%dx%d rss_mb=%s",
                perf_counter() - start,
                geometry.width_px,
                geometry.height_px,
                (
                    f"{rss:.1f}"
                    if (rss := _current_rss_mb()) is not None
                    else "unknown"
                ),
            )
            return image
        finally:
            plt.close(figure)

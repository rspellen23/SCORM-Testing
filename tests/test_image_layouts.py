"""Image layouts — template-faithful framing + the brand image library.

Covers: the brand's built-in image library resolves; image/imagetext render
in every framing mode with a real library image (edge-to-edge, no crash); and
the deck generator offers the image layouts + the library filenames once the
brand library is available by default.
"""
import os

import authoring
import brand as brandmod
import slide_svg


def _render(content, layout="image"):
    b = brandmod.load_brand("teletracking")
    imgdir = authoring.brand_image_dir("teletracking")
    return slide_svg.render_slide_svg(layout, content, b, images_dir=imgdir)


def test_brand_image_dir_resolves_library():
    d = authoring.brand_image_dir("teletracking")
    assert d and os.path.isdir(d)
    files = set(os.listdir(d))
    assert "care-team-discussion.jpg" in files
    assert "best-in-klas-2024-badge.png" in files


def test_brand_image_dir_none_for_brand_without_library():
    assert authoring.brand_image_dir("_default") is None


def test_image_modes_render_with_library_image():
    for mode in ("hero", "full", "banner"):
        svg = _render({"title": "T", "subtitle": "s",
                       "image": "care-team-discussion.jpg", "mode": mode})
        assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
        assert "<image" in svg                      # the real picture landed


def test_imagetext_sides_render_edge_to_edge():
    for side in ("left", "right"):
        svg = _render({"title": "T", "image": "patient-transport.jpg",
                       "side": side, "intro": "i", "items": ["a", "b"]},
                      layout="imagetext")
        assert "<image" in svg


def test_contain_fit_renders_whole_graphic():
    svg = _render({"title": "T", "image": "best-in-klas-2024-badge.png",
                   "mode": "hero", "fit": "contain"})
    assert "<image" in svg


def test_deck_prompt_offers_image_layouts_and_library_files():
    imgs = authoring.list_images(authoring.brand_image_dir("teletracking"))
    assert imgs                                       # library is non-empty
    prompt = authoring.build_deck_prompt("T", "", "", None, "source text",
                                         images=imgs)
    assert "care-team-discussion.jpg" in prompt        # exact filenames injected
    assert "imagetext" in prompt                       # image layouts unlocked

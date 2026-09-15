"""
Generiše ikonicu aplikacije: `ui/icon.ico` i pregled `docs/img/icon.png`.

Pokretanje iz korena repozitorijuma:

    python docs/make_icon.py

Motiv je elisa iz zadatka (`elisa.txt`), presečena po sredini: leva polovina je
gusta mreža u boji originala, desna krupni trouglovi u boji decimiranog modela —
isti par boja koji aplikacija koristi u 3D prikazu. Crta se vektorski, u velikoj
rezoluciji, pa se smanjuje: render mreže bi na 16 px bio mrlja.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
ICO_OUT = REPO / "ui" / "icon.ico"
PNG_OUT = REPO / "docs" / "img" / "icon.png"

S = 2048                      # radno platno; sve mere su u njegovim pikselima
C = S / 2                     # centar

# Iste boje kao u aplikaciji (ui/viewer_widget.py, ui/styles.qss)
TILE_TOP    = (35, 39, 53)
TILE_BOTTOM = (18, 20, 26)
TILE_EDGE   = (46, 49, 64)
ORIG_FILL   = (74, 158, 221)
ORIG_LINE   = (26, 74, 122)
DEC_FILL    = (224, 112, 96)
DEC_LINE    = (138, 48, 32)

BLADES    = 6
R_HUB_IN  = 152              # rupa u sredini glavčine
R_HUB_OUT = 350
GAP       = 26               # prorez između dve polovine

# Profil lopatice, (poluprečnik, poluširina u pikselima): tanak krak iz glavčine
# koji se pri vrhu širi u trougaonu peraju — kao na elisi iz zadatka. Obe veličine
# su linearne po deonicama, pa su ivice prave i mreža ostaje unutar obrisa.
PROFILE = ((290, 42), (552, 57), (828, 276))


def polar(r: float, a: float) -> tuple[float, float]:
    return C + r * math.cos(a), C + r * math.sin(a)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def blade_point(axis: float, u: float, v: float) -> tuple[float, float]:
    """Tačka na lopatici: `u` ide od korena ka vrhu, `v` popreko (0…1)."""
    r = lerp(PROFILE[0][0], PROFILE[-1][0], u)
    for (r0, w0), (r1, w1) in zip(PROFILE, PROFILE[1:]):
        if r <= r1 or (r1, w1) == PROFILE[-1]:
            w = lerp(w0, w1, (r - r0) / (r1 - r0))
            break
    er = (math.cos(axis), math.sin(axis))
    et = (-er[1], er[0])
    off = lerp(-w, w, v)
    return C + er[0] * r + et[0] * off, C + er[1] * r + et[1] * off


def blade_outline(axis: float) -> list[tuple[float, float]]:
    """Obris lopatice: jednom ivicom do vrha, pa nazad drugom."""
    us = [(r - PROFILE[0][0]) / (PROFILE[-1][0] - PROFILE[0][0])
          for r, _ in PROFILE]
    return ([blade_point(axis, u, 0.0) for u in us]
            + [blade_point(axis, u, 1.0) for u in reversed(us)])


def draw_rotor(fill: tuple[int, int, int], line: tuple[int, int, int],
               nu: int, nv: int, hub_sectors: int, lw: int) -> Image.Image:
    """
    Elisa kao RGBA sloj. `nu`/`nv`/`hub_sectors` određuju gustinu mreže —
    gusto za original, grubo za decimirani.
    """
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # Lopatice
    for i in range(BLADES):
        axis = math.radians(-90 + i * 360 / BLADES)
        d.polygon(blade_outline(axis), fill=fill, outline=line, width=lw)

        for iu in range(1, nu):                      # poprečne podele
            u = iu / nu
            d.line([blade_point(axis, u, 0), blade_point(axis, u, 1)],
                   fill=line, width=lw)
        for iv in range(1, nv):                      # uzdužne podele
            v = iv / nv
            d.line([blade_point(axis, 0, v), blade_point(axis, 1, v)],
                   fill=line, width=lw)
        # Dijagonale samo po peraji: u tankom kraku bi bile skoro poprečne i
        # mreža bi se na maloj ikoni pretvorila u šaru.
        for iu in range(nu):
            if iu / nu < 0.5:
                continue
            for iv in range(nv):
                d.line([blade_point(axis, iu / nu, iv / nv),
                        blade_point(axis, (iu + 1) / nu, (iv + 1) / nv)],
                       fill=line, width=lw)

    # Glavčina
    d.ellipse([C - R_HUB_OUT, C - R_HUB_OUT, C + R_HUB_OUT, C + R_HUB_OUT],
              fill=fill, outline=line, width=lw)
    for i in range(hub_sectors):
        a = 2 * math.pi * i / hub_sectors
        d.line([polar(R_HUB_IN, a), polar(R_HUB_OUT, a)], fill=line, width=lw)
    d.ellipse([C - R_HUB_IN, C - R_HUB_IN, C + R_HUB_IN, C + R_HUB_IN],
              fill=(0, 0, 0, 0))                     # rupa: vidi se pozadina
    d.ellipse([C - R_HUB_IN, C - R_HUB_IN, C + R_HUB_IN, C + R_HUB_IN],
              outline=line, width=lw)
    return layer


def tile() -> Image.Image:
    """Tamna zaobljena pločica sa blagim gradijentom — čitljiva i na svetloj traci."""
    grad = Image.new("RGB", (1, S))
    for y in range(S):
        t = y / (S - 1)
        grad.putpixel((0, y), tuple(
            round(lerp(TILE_TOP[i], TILE_BOTTOM[i], t)) for i in range(3)))
    grad = grad.resize((S, S))

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1],
                                           radius=round(S * 0.18), fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    ImageDraw.Draw(out).rounded_rectangle(
        [6, 6, S - 7, S - 7], radius=round(S * 0.18) - 6,
        outline=TILE_EDGE + (255,), width=10)
    return out


def build() -> Image.Image:
    dense  = draw_rotor(ORIG_FILL, ORIG_LINE, nu=4, nv=2, hub_sectors=24, lw=5)
    coarse = draw_rotor(DEC_FILL,  DEC_LINE,  nu=2, nv=1, hub_sectors=6,  lw=8)

    half = Image.new("L", (S, S), 0)
    ImageDraw.Draw(half).rectangle([0, 0, round(C) - 1, S], fill=255)
    rotor = Image.composite(dense, coarse, half)

    # Prorez po sredini — dve polovine ostaju razdvojene i na 16 px.
    ImageDraw.Draw(rotor).rectangle(
        [C - GAP / 2, 0, C + GAP / 2, S], fill=(0, 0, 0, 0))

    icon = tile()
    icon.alpha_composite(rotor)
    return icon


def main() -> int:
    master = build()
    sizes = (256, 128, 64, 48, 32, 24, 16)
    frames = [master.resize((n, n), Image.Resampling.LANCZOS) for n in sizes]

    ICO_OUT.parent.mkdir(parents=True, exist_ok=True)
    PNG_OUT.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(ICO_OUT, format="ICO",
                   sizes=[(n, n) for n in sizes], append_images=frames[1:])
    master.resize((512, 512), Image.Resampling.LANCZOS).save(PNG_OUT)
    print(f"ok {ICO_OUT.relative_to(REPO)}  ({', '.join(f'{n}px' for n in sizes)})")
    print(f"ok {PNG_OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

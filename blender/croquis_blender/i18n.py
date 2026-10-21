# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The panel in Spanish and Portuguese: IngeTrazo Croquis's own words
(core/texts.py), and the few that only Blender's panel says. Blender shows
them when its interface is in one of those languages."""
import bpy

#: Only in Blender's panel.
EXTRA = {
    "es": {
        "Croquis": "Croquis",
        "From": "Desde",
        "Camera": "Cámara",
        "This view": "Esta vista",
        "The scene's camera, at the render's shape": "La cámara de la escena, con la forma del render",
        "What the 3D viewport shows": "Lo que muestra la vista 3D",
        "Width": "Ancho",
        "S": "S", "M": "M", "L": "L",
        "1600 pixels wide": "1600 píxeles de ancho",
        "2400 pixels wide": "2400 píxeles de ancho",
        "3600 pixels wide": "3600 píxeles de ancho",
        "A width of your own": "Un ancho a tu medida",
        "The drawing's width in pixels": "El ancho del dibujo en píxeles",
        "Your own choices": "Tus propias elecciones",
        "Technique and light": "Técnica y luz",
        "Composition and paper": "Composición y papel",
        "Image": "Imagen",
        "An image of your own as the paper": "Una imagen tuya como papel",
        "From a ruler (0) to a loose hand (100)": "De la regla (0) a la mano suelta (100)",
        "Outlines heavier than the edges inside": "Siluetas más marcadas que las aristas de adentro",
        "Some lines drawn twice": "Algunas líneas repasadas",
        "Long lines broken where the pen was lifted": "Las líneas largas cortadas donde se levantó la pluma",
        "Strokes of alcohol marker": "Trazos de rotulador",
        "Washes of watercolour": "Aguadas de acuarela",
        "Lines only, no colour": "Solo líneas, sin color",
        "From the upper left, as a sketcher draws": "Desde arriba a la izquierda, como dibuja un croquista",
        "The scene's Sun lamp": "La lámpara Sun de la escena",
        "Cast shadows, on the model and the ground": "Sombras arrojadas, sobre el modelo y el suelo",
        "Each material in the nearest marker": "Cada material con el rotulador más cercano",
        "Each material by how light it is": "Cada material según lo claro que es",
        "Light and shade only, the shade near black": "Solo luz y sombra, la sombra casi negra",
        "No material colour": "Sin color de material",
        "High contrast: the black breaks up at its edges": "Alto contraste: el negro se rompe en sus bordes",
        "Each area of colour or hatching its own slant": "Cada zona de color o rayado con su propia inclinación",
        "Hatch the shade in ink": "Rayar la sombra a tinta",
        "Along each face (off: one diagonal)": "A lo largo de cada cara (apagado: una diagonal)",
        "Turn the hatching": "Girar el rayado",
        "The colour thins out toward the edges": "El color se desvanece hacia los bordes",
        "Some lines run on as construction lines": "Algunas líneas siguen como líneas de construcción",
        "Loose strokes on the ground": "Trazos sueltos en el suelo",
        "Draw the view as a freehand sketch": "Dibujar la vista como un croquis a mano alzada",
        "Save the drawing…": "Guardar el dibujo…",
        "Save the last drawing as PNG, SVG in layers or PDF": "Guardar el último dibujo en PNG, SVG por capas o PDF",
        "Format": "Formato",
        "PNG": "PNG",
        "SVG in layers": "SVG por capas",
        "PDF": "PDF",
        "The drawing as a picture": "El dibujo como imagen",
        "Paper, colour and the ink as vector paths": "Papel, color y la tinta en trazos vectoriales",
        "One page at 300 dpi, the ink as vector paths": "Una página a 300 ppp, la tinta en trazos vectoriales",
        "Your image": "Tu imagen",
        "An image of your own": "Una imagen tuya",
        "The scene has no camera: add one, or draw from this view":
            "La escena no tiene cámara: agrega una, o dibuja desde esta vista",
        "No 3D viewport to draw from": "No hay una vista 3D desde la cual dibujar",
        "Nothing to draw: the scene has no visible mesh": "Nada que dibujar: la escena no tiene mallas visibles",
        "Croquis: {w}×{h} in {s} s": "Croquis: {w}×{h} en {s} s",
        "Saved {path}": "Guardado: {path}",
    },
    "pt-BR": {
        "Croquis": "Croquis",
        "From": "De",
        "Camera": "Câmera",
        "This view": "Esta vista",
        "The scene's camera, at the render's shape": "A câmera da cena, com a forma do render",
        "What the 3D viewport shows": "O que a vista 3D mostra",
        "Width": "Largura",
        "S": "S", "M": "M", "L": "L",
        "1600 pixels wide": "1600 pixels de largura",
        "2400 pixels wide": "2400 pixels de largura",
        "3600 pixels wide": "3600 pixels de largura",
        "A width of your own": "Uma largura sob medida",
        "The drawing's width in pixels": "A largura do desenho em pixels",
        "Your own choices": "Suas próprias escolhas",
        "Technique and light": "Técnica e luz",
        "Composition and paper": "Composição e papel",
        "Image": "Imagem",
        "An image of your own as the paper": "Uma imagem sua como papel",
        "From a ruler (0) to a loose hand (100)": "Da régua (0) à mão solta (100)",
        "Outlines heavier than the edges inside": "Silhuetas mais marcadas que as arestas de dentro",
        "Some lines drawn twice": "Algumas linhas repassadas",
        "Long lines broken where the pen was lifted": "As linhas longas cortadas onde a caneta foi levantada",
        "Strokes of alcohol marker": "Traços de marcador",
        "Washes of watercolour": "Aguadas de aquarela",
        "Lines only, no colour": "Só linhas, sem cor",
        "From the upper left, as a sketcher draws": "De cima à esquerda, como desenha quem faz croquis",
        "The scene's Sun lamp": "A lâmpada Sun da cena",
        "Cast shadows, on the model and the ground": "Sombras projetadas, no modelo e no chão",
        "Each material in the nearest marker": "Cada material com o marcador mais próximo",
        "Each material by how light it is": "Cada material conforme o quanto é claro",
        "Light and shade only, the shade near black": "Só luz e sombra, a sombra quase preta",
        "No material colour": "Sem cor de material",
        "High contrast: the black breaks up at its edges": "Alto contraste: o preto se quebra nas bordas",
        "Each area of colour or hatching its own slant": "Cada área de cor ou hachura com sua própria inclinação",
        "Hatch the shade in ink": "Hachurar a sombra a nanquim",
        "Along each face (off: one diagonal)": "Ao longo de cada face (desligado: uma diagonal)",
        "Turn the hatching": "Girar a hachura",
        "The colour thins out toward the edges": "A cor some em direção às bordas",
        "Some lines run on as construction lines": "Algumas linhas continuam como linhas de construção",
        "Loose strokes on the ground": "Traços soltos no chão",
        "Draw the view as a freehand sketch": "Desenhar a vista como um croqui à mão livre",
        "Save the drawing…": "Salvar o desenho…",
        "Save the last drawing as PNG, SVG in layers or PDF": "Salvar o último desenho em PNG, SVG em camadas ou PDF",
        "Format": "Formato",
        "PNG": "PNG",
        "SVG in layers": "SVG em camadas",
        "PDF": "PDF",
        "The drawing as a picture": "O desenho como imagem",
        "Paper, colour and the ink as vector paths": "Papel, cor e o nanquim em traços vetoriais",
        "One page at 300 dpi, the ink as vector paths": "Uma página a 300 dpi, o nanquim em traços vetoriais",
        "Your image": "Sua imagem",
        "An image of your own": "Uma imagem sua",
        "The scene has no camera: add one, or draw from this view":
            "A cena não tem câmera: adicione uma, ou desenhe desta vista",
        "No 3D viewport to draw from": "Não há uma vista 3D de onde desenhar",
        "Nothing to draw: the scene has no visible mesh": "Nada a desenhar: a cena não tem malhas visíveis",
        "Croquis: {w}×{h} in {s} s": "Croquis: {w}×{h} em {s} s",
        "Saved {path}": "Salvo: {path}",
    },
}

#: Blender's language codes → the catalogue's.
LOCALES = {"es": "es", "pt_BR": "pt-BR", "pt": "pt-BR"}
#: Blender looks a label up in its context; ours have these.
CONTEXTS = ("*", "Operator")


def _table() -> dict:
    from .core import texts
    out = {}
    for blender_code, ours in LOCALES.items():
        words = dict(texts._TEXTS.get(ours, {}))
        words.update(EXTRA.get(ours, {}))
        out[blender_code] = {(ctx, en): tr for en, tr in words.items()
                             for ctx in CONTEXTS if en and tr}
    return out


def tr(text: str, **kw) -> str:
    """A message in the interface's language (for reports, which Blender
    does not translate by itself)."""
    out = bpy.app.translations.pgettext_iface(text)
    return out.format(**kw) if kw else out


def register() -> None:
    bpy.app.translations.register(__package__, _table())


def unregister() -> None:
    bpy.app.translations.unregister(__package__)

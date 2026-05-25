"""Script para actualizar todos los botones con los iconos de png_botones"""
import os
import sys

# Este script se ejecuta una vez para verificar que los iconos están
# La app los carga desde: src/ui/icons/png_botones/

icons_needed = [
    "play.png", "pause.png", "stop.png", "mute.png", "live.png",
    "agregar.png", "delete.png", "guardar.png", "cargar.png",
    "buscar.png", "enviar_pre.png", "camara_vivo.png",
    "pantalla.png", "detectar.png", "mezclar.png",
    "tema_oscuro.png", "tema_claro.png", "carpeta.png",
    "pip_a.png", "pip_b.png"
]

folder = os.path.dirname(__file__)
for icon in icons_needed:
    path = os.path.join(folder, icon)
    if os.path.exists(path):
        print(f"  OK: {icon}")
    else:
        print(f"  FALTA: {icon}")

print("\nTodos los iconos se cargan desde: src/ui/icons/png_botones/")

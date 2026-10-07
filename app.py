cat << 'EOF' > app.py
from flask import Flask, render_template, request
import requests
import re

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "REST-Range": "resources=0-24"
}

CONFIG_SUPERS = [
    {"nombre": "Día Online", "url": "https://diaonline.supermercadosdia.com.ar", "clase": "dia"},
    {"nombre": "Carrefour", "url": "https://www.carrefour.com.ar", "clase": "carrefour"},
    {"nombre": "Mas Online", "url": "https://www.masonline.com.ar", "clase": "masonline"},
    {"nombre": "Vea Online", "url": "https://www.vea.com.ar", "clase": "vea"}
]

def extraer_promocion(comm):
    promos_texto = []
    
    teasers = comm.get("Teasers", [])
    for t in teasers:
        if isinstance(t, dict):
            nombre_promo = t.get("name") or t.get("<Name>k__BackingField") or t.get("generalValues", {}).get("name")
            if nombre_promo:
                promos_texto.append(str(nombre_promo))

    highlights = comm.get("DiscountHighLight", {})
    if isinstance(highlights, dict):
        for k, v in highlights.items():
            if isinstance(v, dict) and "name" in v:
                promos_texto.append(str(v["name"]))

    return " | ".join(promos_texto).upper()


def calcular_precio_promo(p_lista, p_final, texto_promo, nombre_producto):
    texto_completo = f"{texto_promo} {nombre_producto}".upper()
    
    match_2do = re.search(r'(?:2DO|SEGUNDA|2DA).*?(\d{2})%', texto_completo)
    if match_2do:
        pct_descuento_2da = float(match_2do.group(1))
        factor_unidad = (100.0 + (100.0 - pct_descuento_2da)) / 200.0
        return round(p_lista * factor_unidad, 2)

    if "2X1" in texto_completo:
        return round(p_lista * 0.5, 2)

    if "3X2" in texto_completo:
        return round(p_lista * (2/3), 2)

    return p_final


def extraer_categoria_tamano(nombre):
    nombre_clean = nombre.lower().replace(",", ".")
    
    subtipo = "estandar"
    if any(k in nombre_clean for k in ["zero", "sin azucar", "sin azúcar"]):
        subtipo = "zero"
    elif any(k in nombre_clean for k in ["liviano", "menos azucares", "menos azúcares", "light"]):
        subtipo = "liviano"

    match = re.search(r'(\d+(?:\.\d+)?)\s*(g|gr|grs|gramos|kg|kilo|kilos|ml|lt|lts|litros?|l)\b', nombre_clean)
    if match:
        cant = float(match.group(1))
        unidad = match.group(2)
        
        if unidad in ["g", "gr", "grs", "gramos"]:
            cant_std = int(cant)
            tamano_label = f"{cant_std}g"
        elif unidad in ["kg", "kilo", "kilos"]:
            cant_std = int(cant * 1000)
            tamano_label = f"{cant_std}g"
        elif unidad in ["l", "lt", "lts", "litros"]:
            cant_std = int(cant * 1000)
            tamano_label = f"{cant_std}ml"
        elif unidad == "ml":
            cant_std = int(cant)
            tamano_label = f"{cant_std}ml"
        
        categoria_clave = f"{tamano_label}_{subtipo}"
        return categoria_clave, cant_std, subtipo

    return f"{re.sub(r'[^a-z0-9]', '', nombre_clean)}_{subtipo}", 999999, subtipo


def cumple_filtro_busqueda(nombre_prod, marca_prod, termino_busqueda):
    stopwords = {"de", "del", "la", "las", "el", "los", "en", "para", "con", "sin", "y", "a"}
    
    palabras_busqueda = set(re.findall(r'\w+', termino_busqueda.lower())) - stopwords
    texto_evaluar = f"{nombre_prod} {marca_prod}".lower()
    
    for palabra in palabras_busqueda:
        if palabra not in texto_evaluar:
            return False
            
    return True


def obtener_precios_super(termino):
    resultados = []
    termino_url = requests.utils.quote(termino)
    
    for super_info in CONFIG_SUPERS:
        url = f"{super_info['url']}/api/catalog_system/pub/products/search/{termino_url}?_from=0&_to=24"
        try:
            res = requests.get(url, headers=HEADERS, timeout=8)
            if res.status_code in (200, 206):
                for prod in res.json():
                    nombre = prod.get("productName", "")
                    marca = prod.get("brand", "")
                    
                    if not cumple_filtro_busqueda(nombre, marca, termino):
                        continue

                    link_text = prod.get("linkText", "")
                    link_raw = prod.get("link", "")
                    
                    if link_raw and link_raw.startswith("http"):
                        link_producto = link_raw
                    elif link_text:
                        link_producto = f"{super_info['url']}/{link_text}/p"
                    else:
                        link_producto = super_info['url']

                    items = prod.get("items", [])
                    if items:
                        sellers = items[0].get("sellers", [])
                        if sellers:
                            comm = sellers[0].get("commertialOffer", {})
                            p_lista = comm.get("ListPrice", 0)
                            p_final = comm.get("Price", 0)
                            disponible = comm.get("IsAvailable", False)
                            
                            texto_promo = extraer_promocion(comm)
                            p_lista_real = p_lista if p_lista > p_final else p_final
                            
                            p_final_calculado = calcular_precio_promo(p_lista_real, p_final, texto_promo, nombre)

                            if disponible and p_final_calculado > 0:
                                descuento = round((1 - p_final_calculado / p_lista_real) * 100) if p_lista_real > p_final_calculado else 0
                                categoria_tamano, tamano_num, subtipo = extraer_categoria_tamano(nombre)
                                
                                resultados.append({
                                    "supermercado": super_info["nombre"],
                                    "clase_css": super_info["clase"],
                                    "producto": nombre,
                                    "link": link_producto,
                                    "categoria_tamano": categoria_tamano,
                                    "tamano_num": tamano_num,
                                    "subtipo": subtipo,
                                    "marca": marca,
                                    "precio_lista": p_lista_real,
                                    "precio_final": p_final_calculado,
                                    "descuento": descuento,
                                    "promocion": texto_promo if texto_promo else "Sin promo especial",
                                    "es_mejor_precio": False
                                })
        except Exception:
            continue

    precios_minimos_por_categoria = {}
    for item in resultados:
        cat = item["categoria_tamano"]
        precio = item["precio_final"]
        if cat not in precios_minimos_por_categoria or precio < precios_minimos_por_categoria[cat]:
            precios_minimos_por_categoria[cat] = precio

    categorias_ya_marcadas = set()
    resultados.sort(key=lambda x: x["precio_final"])

    for item in resultados:
        cat = item["categoria_tamano"]
        if item["precio_final"] == precios_minimos_por_categoria[cat] and cat not in categorias_ya_marcadas:
            item["es_mejor_precio"] = True
            categorias_ya_marcadas.add(cat)

    resultados.sort(key=lambda x: (x["tamano_num"], x["subtipo"], x["precio_final"]))

    return resultados

@app.route('/', methods=['GET', 'POST'])
def inicio():
    busqueda = ""
    resultados = []

    if request.method == 'POST':
        busqueda = request.form.get('busqueda', '').strip()
        if busqueda:
            resultados = obtener_precios_super(busqueda)

    return render_template('index.html', busqueda=busqueda, resultados=resultados)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
EOF

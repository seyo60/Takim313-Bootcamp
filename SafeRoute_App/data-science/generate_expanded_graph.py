# data-science/generate_expanded_graph.py
"""
backend/generate_test_graph.py'nin devami: rota grafini "Loop, Chicago"
disina genisletir. Render ucretsiz plani (512 MB RAM) sinirini gozeterek
KADEMELI ilerlenir - tek seferde tum sehir INDIRILMEZ.

Bu script SADECE dosya uretir; backend/backend_test_graph.graphml'in
UZERINE YAZMAZ ve backend/.env'deki GRAPH_PATH'i DEGISTIRMEZ. Uretilen
dosya once boyut/node-edge sayisi acisindan degerlendirilir, guvenli
bulunursa Seymen tarafindan devreye alinir.

Adim 1 bbox'i, gercek risk verisindeki (chicago_clean_data.csv) en yogun
kumelerden secildi: mevcut Loop grafinin (41.8675-41.8886, -87.6379--87.6101)
hemen BATISINI da kapsayacak sekilde genisletildi - cunku en yogun risk
hucrelerinden biri zaten Loop icinde, digeri tam bitisiginde (West Loop /
Near West Side).
"""
import os
import socket
import osmnx as ox

# KOK NEDEN (tespit edildi): overpass-api.de hem IPv6 hem IPv4 DNS kaydina
# sahip. Python 'requests' varsayilan olarak once IPv6'yi deniyor, ama bu
# ortamda IPv6 cikisi yok - bu yuzden ConnectTimeout (600s) ile bekliyordu.
# curl etkilenmiyordu cunku farkli bir baglanti stratejisi kullaniyor.
# Cozum: DNS cozumlemesini IPv4 ile sinirla.
_original_getaddrinfo = socket.getaddrinfo
def _ipv4_only_getaddrinfo(host, *args, **kwargs):
    return [r for r in _original_getaddrinfo(host, *args, **kwargs) if r[0] == socket.AF_INET]
socket.getaddrinfo = _ipv4_only_getaddrinfo

ox.settings.requests_timeout = 300

# Adim 1: Loop + hemen batisi. Mevcut Loop bbox'ini TAMAMEN icerir (superset),
# yani bu dosya eskisinin yerine dogrudan gecebilir (iki ayri graf birlestirmeye
# gerek yok).
BBOX = {
    "north": 41.91,
    "south": 41.85,
    "east": -87.60,
    "west": -87.68,
}
OUTPUT_PATH = "chicago_west_loop_expanded.graphml"

# Guvenlik esigi: mevcut Loop grafi 6.1 MB / 512 MB RAM planinda sorunsuz.
# Bunun katbekat uzerine cikarsa (kaba kural: ~50 MB), Seymen ile RAM testi
# yapilmadan devreye ALINMAMALI.
SIZE_WARNING_MB = 50


def main():
    print(f"Bolge indiriliyor: {BBOX}")
    print("(Bu OSM Overpass API'sinden cekiliyor, alan buyuklugune gore birkaç dakika surebilir...)")
    # DIKKAT: kurulu osmnx versiyonunda bbox parametresi
    # (left, bottom, right, top) yani (west, south, east, north) sirasi
    # bekliyor - (north, south, east, west) DEGIL. Yanlis sira, OSMnx'in
    # az önce neredeyse tüm dünyayı kapsayan geçersiz bir alan sanmasına ve
    # Overpass API'sinde timeout'a yol açmıştı.
    G = ox.graph_from_bbox(
        bbox=(BBOX["west"], BBOX["south"], BBOX["east"], BBOX["north"]),
        network_type="walk",
    )
    ox.save_graphml(G, filepath=OUTPUT_PATH)

    file_size_mb = os.path.getsize(OUTPUT_PATH) / (1024 * 1024)
    node_count = len(G.nodes)
    edge_count = len(G.edges)

    print("\n--- SONUC ---")
    print(f"Dosya: {OUTPUT_PATH}")
    print(f"Dosya boyutu: {file_size_mb:.2f} MB  (referans: Loop tek basina 6.1 MB)")
    print(f"Kavşak: {node_count}  (referans: Loop tek basina 5430)")
    print(f"Sokak parçası: {edge_count}  (referans: Loop tek basina 14854)")

    if file_size_mb > SIZE_WARNING_MB:
        print(f"\nUYARI: Dosya {SIZE_WARNING_MB} MB esiginin uzerinde.")
        print("   Render'in 512 MB ucretsiz planinda RAM testi yapmadan DEVREYE ALMA.")
    else:
        print(f"\nEsigin altinda. Yine de Seymen'in lokalinde gercek RAM kullanimini")
        print("   olcmesi onerilir (GraphML dosya boyutu RAM kullanimiyla birebir orantili degildir).")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Render the documentation's editable, top-view SVG wiring illustration.

No third-party dependencies. Pin assignments follow docs/hardware-block-diagram.md.
Board artwork is illustrative, based on the linked vendor pin maps and photos.
"""
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/images/hardware-wiring.svg"
items = []


def add(s):
    items.append(s)


def rect(x, y, w, h, fill, stroke="none", radius=12):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')


def text(x, y, s, size=20, color="#24364b", weight=400, anchor="start"):
    add(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}">{escape(s)}</text>')


def circle(x, y, r, fill, stroke="none", sw=2):
    add(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def pad(x, y, label, dx=0, dy=0, anchor="start"):
    circle(x, y, 10, "#e0bb6c")
    circle(x, y, 5, "#263038")
    if label:
        text(x + dx, y + dy, label, 18, "#ffffff", 600, anchor)


def wire(points, color, width=5, dash=False):
    coords = " ".join(f"{x},{y}" for x, y in points)
    add(f'<polyline points="{coords}" fill="none" stroke="#f6f8fb" stroke-width="{width+5}" stroke-linejoin="round" stroke-linecap="round"/>')
    d = ' stroke-dasharray="10 9"' if dash else ""
    add(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"{d}/>')


def label(x, y, s, color, size=18):
    w = len(s) * size * .56 + 18
    rect(x-7, y-size, w, size+9, "#f6f8fb", radius=5)
    text(x+2, y, s, size, color, 600)


V3 = "#d83b42"
V5 = "#e17619"
GND = "#303f4d"
SDA = "#008e95"
SCL = "#1775c1"
MOSI = "#9b45ae"
MISO = "#3259b7"
CLK = "#bc8400"
CS = "#207d52"
DET = "#738799"
TX = "#009966"
RX = "#4261d0"
SLNT = "#b55194"

add('<svg xmlns="http://www.w3.org/2000/svg" width="2000" height="1650" viewBox="0 0 2000 1650" role="img" aria-labelledby="title desc">')
add('<title id="title">Humanoid Joint Diagnostics Kit: top-view module wiring</title>')
add('<desc id="desc">XIAO ESP32-C5 wired to CAN Pal 5708, microSD breakout 4682, DS3231 RTC and Hshop 5 V DC-DC supply. Individual signal wires and shared 3.3 V and ground rails are shown. See the adjacent Markdown connection table for the complete net list and supply limitations.</desc>')
add('<g font-family="Arial, Helvetica, sans-serif">')
rect(0, 0, 2000, 1650, "#f6f8fb", radius=0)
text(70, 68, "HUMANOID JOINT DIAGNOSTICS KIT", 18, "#55718d", 700)
text(70, 122, "Module wiring · top view", 44, "#172d44", 700)
text(70, 158, "Pin labels are authoritative. Illustrative board artwork; modules enlarged independently, not to scale.", 21)

rect(70, 188, 935, 83, "#e9eef5")
text(90, 218, "POWER: orange = 5 V     red = 3.3 V     dark grey = common GND", 20, weight=600)
text(90, 249, "Dots = electrical joins. Crossings without dots are NOT connected. Dashed DET = optional.", 18)

# DC supply and selected converter, drawn by function because its header has no
# unambiguous primary-source pin numbering.
text(1520, 143, "Hshop HS1436 · DC-DC module", 24, weight=700)
rect(1520, 170, 360, 180, "#22674f", "#164635")
rect(1730, 185, 120, 74, "#8d9598", "#3b484b", 5)
text(1790, 232, "220", 28, "#26343b", 700, "middle")
rect(1590, 187, 88, 62, "#20282f", radius=4)
text(1700, 281, "4.5–5 V OUT · 1 A max", 21, "#ffffff", 600, "middle")
for x, name in [(1580,"IN"),(1700,"GND"),(1820,"OUT")]:
    pad(x,325,name,0,-16,"middle")
rect(1130, 173, 290, 109, "#ffffff", "#b7c6d4")
text(1150, 207, "External DC source", 22, weight=700)
text(1150, 239, "5.5–32 V DC input", 20)
text(1150, 267, "+ / −   Check polarity", 18)
text(1393, 229, "+", 22, V5, 700)
text(1393, 266, "−", 22, GND, 700)

# RTC: component side; six-pin header rotated to right. Reversed order follows
# 180-degree rotation of the seller's ZS-042 component-side photo.
text(150, 370, "Nshop DS3231 RTC · ZS-042 style", 24, weight=700)
rect(140, 390, 420, 230, "#185e8c", "#0b436a")
for x,y in [(165,415),(165,590),(530,590)]:
    circle(x,y,11,"#c4ccd1"); circle(x,y,6,"#f6f8fb")
rect(250, 420, 140, 95, "#252e35", radius=4)
text(320, 475, "DS3231", 24, "#e6edf1",600,"middle")
rect(245, 550, 93, 40, "#252e35", radius=4)
text(291,577,"AT24C32",15,"#e6edf1",400,"middle")
text(155,648,"Battery holder is on the reverse side.",18)
for i,name in enumerate(["GND","VCC","SDA","SCL","SQW","32K"]):
    pad(540,410+i*30,name,-20,6,"end")
text(465,661,"SQW / 32K: no wire",17,"#57718b")

# MCU: actual USB-up XIAO header order.
text(857, 418, "Seeed XIAO ESP32-C5", 25, weight=700)
rect(890, 482, 260, 420, "#243d36", "#142c25", 18)
rect(959, 454, 122, 66, "#c5cbd1", "#647582", 7)
rect(973, 461, 94, 25, "#34434d", radius=5)
rect(950, 552, 140, 249, "#d2d9db", "#8f9ea4", 7)
text(1020,625,"XIAO",27,"#263a46",700,"middle")
text(1020,665,"ESP32-C5",21,"#263a46",600,"middle")
text(1020,704,"Wi-Fi",20,"#263a46",400,"middle")
text(1020,735,"CAN FD",20,"#263a46",400,"middle")
for x in [966,1075]:
    rect(x,840,30,25,"#bbc5c9",radius=3)
circle(1020,854,12,"#d8b36b")
text(852,944,"USB up · antenna connector down",19)
text(862,972,"D3 unused · attach supplied antenna",18)
left = ["D0","D1","D2","D3","D4","D5","D6"]
right = ["5V","GND","3V3","D10","D9","D8","D7"]
for i,(l,r) in enumerate(zip(left,right)):
    y=535+i*55
    pad(910,y,l,16,6)
    pad(1130,y,r,-16,6,"end")

# microSD: 90 degrees clockwise from the vendor's socket-up photograph.
text(1450, 526, "Adafruit 4682 · microSD", 25, weight=700)
text(1450, 556, "3.3 V ONLY · SPI wiring", 20, V3, 700)
rect(1480, 590, 390, 445, "#273138", "#101b21")
rect(1630, 660, 221, 270, "#c9d1d5", "#84929b", 6)
rect(1815, 683, 41, 224, "#45545e", radius=2)
text(1752,801,"microSD",27,"#3d505e",600,"middle")
text(1752,835,"socket",23,"#3d505e",400,"middle")
for x,y in [(1834,624),(1834,998)]:
    circle(x,y,14,"#d2b577"); circle(x,y,9,"#f6f8fb")
sd_labels=["3V","GND","CLK","SO / D0","SI / CMD","CS / D3","D1","DAT2","DET"]
for i,name in enumerate(sd_labels):
    pad(1510,620+i*46,name,20,6)
text(1478,1073,"Use SPI pins; D1 and DAT2 are unconnected.",18)

# CAN Pal: terminal block up; header order matches current vendor photo.
rect(140, 920, 370, 292, "#273138", "#101b21")
rect(196, 925, 248, 76, "#39a470", "#167247", 5)
for x,name in [(232,"L"),(320,"GND"),(408,"H")]:
    circle(x,950,18,"#d8e3df","#58756b")
    add(f'<path d="M{x-10},958 l20,-16" stroke="#5a736b" stroke-width="4"/>')
    text(x,985,name,18,"#f5fff9",600,"middle")
text(325,1027,"Adafruit CAN Pal · 5708",21,"#ffffff",700,"middle")
rect(202, 1040, 112, 80, "#131e25", radius=4)
text(258,1085,"TJA1051",18,"#e4ecef",600,"middle")
rect(351, 1040, 111, 50, "#b8c4c9", radius=5)
rect(414, 1049, 37, 29, "#26343c", radius=3)
text(405,1102,"TERM OFF*",16,"#ffffff",600,"middle")
for i,name in enumerate(["Vcc","GND","RX","TX","SLNT","CANH","CANL"]):
    pad(178+48*i,1180,"")
    text(178+48*i,1161,name,15,"#ffffff",600,"middle")

# Target bus connection.
rect(140, 717, 395, 105, "#e5edf2", "#b8c7d1")
text(160,750,"Target CAN bus",24,weight=700)
text(232,798,"CANL",18,anchor="middle")
text(320,798,"GND",18,anchor="middle")
text(408,798,"CANH",18,anchor="middle")
wire([(232,814),(232,950)],"#bd9300")
wire([(320,814),(320,950)],GND)
wire([(408,814),(408,950)],"#3288a8")

# Shared power rails and all physical branch connections.
wire([(110,310),(1390,310)],V3,7)
wire([(80,340),(1360,340)],GND,7)
wire([(1130,645),(1290,645),(1290,310)],V3)
wire([(1130,590),(1260,590),(1260,340)],GND)
wire([(540,440),(600,440),(600,310)],V3)
wire([(540,410),(580,410),(580,340)],GND)
wire([(1510,620),(1390,620),(1390,310)],V3)
wire([(1510,666),(1360,666),(1360,340)],GND)
wire([(178,1180),(178,1240),(110,1240),(110,310)],V3)
wire([(226,1180),(226,1266),(80,1266),(80,340)],GND)

# External power only; disconnect OUT before attaching a powered USB cable.
wire([(1420,225),(1460,225),(1460,365),(1580,365),(1580,325)],V5)
wire([(1420,260),(1430,260),(1430,380),(1700,380),(1700,325)],GND)
wire([(1260,340),(1260,380),(1430,380)],GND)
wire([(1820,325),(1908,325),(1908,417),(1190,417),(1190,535),(1130,535)],V5)
label(1680,403,"5 V → XIAO 5V",V5)
text(1550,451,"Converter terminals shown by function.",18)
text(1550,478,"Confirm IN / GND / OUT on your unit.",18)

# RTC signals.
wire([(910,755),(683,755),(683,470),(540,470)],SDA)
wire([(910,810),(650,810),(650,500),(540,500)],SCL)
text(150,687,"SDA: D4 / GPIO23",19,SDA,600)
text(375,687,"SCL: D5 / GPIO24",19,SCL,600)

# SD signal routing. Clock, SO and SI terminate at the SPI-labelled pads.
wire([(1130,700),(1410,700),(1410,804),(1510,804)],MOSI)
wire([(1130,755),(1380,755),(1380,758),(1510,758)],MISO)
wire([(1130,810),(1440,810),(1440,712),(1510,712)],CLK)
wire([(910,590),(815,590),(815,1010),(1410,1010),(1410,850),(1510,850)],CS)
wire([(910,535),(782,535),(782,1040),(1440,1040),(1440,988),(1510,988)],DET,4,True)
label(1157,690,"D10 / GPIO10 → SI",MOSI,17)
label(1157,746,"D9 / GPIO9 → SO",MISO,17)
label(1157,802,"D8 / GPIO8 → CLK",CLK,17)
label(928,1001,"D1 / GPIO0 → CS",CS)
label(928,1065,"D0 / GPIO1 → DET (optional)",DET)

# CAN controller signals, including a branched SLNT pull-up.
wire([(910,865),(738,865),(738,1300),(322,1300),(322,1180)],TX)
wire([(1130,865),(1230,865),(1230,1334),(274,1334),(274,1180)],RX)
wire([(910,645),(710,645),(710,1368),(370,1368),(370,1180)],SLNT)
label(492,1290,"D6 / GPIO11 → TX",TX)
label(802,1324,"RX → D7 / GPIO12",RX)
label(482,1358,"D2 / GPIO25 → SLNT",SLNT)
wire([(110,310),(110,1110),(579,1110)],V3)
wire([(634,1110),(710,1110)],SLNT)
rect(579,1099,55,22,"#ebd8af","#ab8961",2)
text(579,1087,"10 kΩ",19,weight=600)
text(567,1150,"SLNT pull-up",18)

# Joins and connection dots. Crossing wires without a dot are not connected.
for x,y,c in [(110,310,V3),(600,310,V3),(1290,310,V3),(1390,310,V3),(110,1110,V3),
              (80,340,GND),(580,340,GND),(1260,340,GND),(1360,340,GND),(1430,380,GND),
              (710,1110,SLNT)]:
    circle(x,y,6,c,"#f6f8fb",1)
label(740,300,"3.3 V distribution",V3)
label(742,365,"COMMON GND",GND)

# Each wire ends on a visible gold pad with a coloured solder point.
for x,y,c in [(1130,535,V5),(1130,590,GND),(1130,645,V3),(540,410,GND),(540,440,V3),
 (540,470,SDA),(540,500,SCL),(910,755,SDA),(910,810,SCL),(1510,620,V3),(1510,666,GND),
 (1130,700,MOSI),(1510,804,MOSI),(1130,755,MISO),(1510,758,MISO),(1130,810,CLK),(1510,712,CLK),
 (910,590,CS),(1510,850,CS),(910,535,DET),(1510,988,DET),(910,865,TX),(322,1180,TX),
 (1130,865,RX),(274,1180,RX),(910,645,SLNT),(370,1180,SLNT),(178,1180,V3),(226,1180,GND)]:
    circle(x,y,5,c,"#f9f3d6",1)

rect(70, 1420, 1860, 165, "#e8edf3")
text(96,1453,"BEFORE POWERING",18,"#405a73",700)
text(96,1489,"1  Disconnect converter OUT from XIAO before plugging in powered USB. Measure the converter output first.",22,weight=600)
text(96,1525,"2  RTC: verify battery and charging path; do not charge a CR2032. SD and RTC firmware support is still planned.",21)
text(96,1561,"3  *CAN termination OFF on an already terminated bus; ON only at an endpoint needing 120 Ω. CAN is not isolated.",21)
text(75,1623,"Sources and exact wire table: docs/hardware-block-diagram.md  •  Hardware operation and combined power budget remain unvalidated.",19,"#5d748a")
add('</g></svg>')
OUT.write_text("\n".join(items)+"\n")
print(OUT)

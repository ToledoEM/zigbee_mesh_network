from pathlib import Path

import pandas as pd
import networkx as nx
from pyvis.network import Network

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

nodes = pd.read_csv(BASE_DIR / "nodes.csv")
edges = pd.read_csv(BASE_DIR / "edges.csv")

G = nx.DiGraph()
G.add_nodes_from(nodes["id"].tolist())

def _lqi_to_width(lqi):
    try:
        v = float(lqi)
    except (TypeError, ValueError):
        return 1.0
    return 1.0 + (max(0.0, min(v, 255.0)) / 255.0) * 6.0


def _lqi_to_ratio(lqi):
    try:
        v = float(lqi)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(v, 255.0)) / 255.0


def _interp_color(start_rgb, end_rgb, t):
    r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * t)
    g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * t)
    b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * t)
    return r, g, b


NODE_STYLES = {
    "Coordinator": {"color": "#f18c2f", "borderWidth": 2, "font": {"size": 12}},
    "Router": {"color": "#f3a23a", "borderWidth": 1, "font": {"size": 11}},
    "EndDevice": {"color": "#5bb8e3", "borderWidth": 1, "font": {"size": 11}},
}
NODE_LEVELS = {
    "Coordinator": 0,
    "Router": 1,
    "EndDevice": 2,
}

for _, r in edges.iterrows():
    src = r.get("source")
    tgt = r.get("target")
    if pd.isna(src) or pd.isna(tgt):
        continue
    lqi = r.get("lqi")
    width = _lqi_to_width(lqi)
    ratio = _lqi_to_ratio(lqi)
    r_c, g_c, b_c = _interp_color((235, 87, 125), (244, 162, 89), ratio)
    edge_color = f"rgba({r_c}, {g_c}, {b_c}, 0.45)"
    G.add_edge(
        src,
        tgt,
        lqi=lqi,
        width=width,
        value=width,
        arrows="to",
        color=edge_color,
        smooth={"type": "cubicBezier", "roundness": 0.65},
    )
for _, r in nodes.iterrows():
    if r["id"] in G:
        label = str(r.get("label", r["id"])).strip()
        device_type = str(r.get("device_type", "")).strip()
        style = NODE_STYLES.get(device_type, {})
        level = NODE_LEVELS.get(device_type, 3)
        G.nodes[r["id"]].update(
            {
                "label": label,
                "device_type": device_type,
                "shape": "box",
                "margin": 6,
                "level": level,
                "font": {
                    "face": "Arial",
                    "color": "#1f1f1f",
                    "size": 10,
                },
                "color": style.get("color", "#d9d9d9"),
                "borderWidth": style.get("borderWidth", 1),
                "widthConstraint": {"maximum": 140},
            }
        )
        if "font" in style:
            G.nodes[r["id"]]["font"].update(style["font"])

net = Network(height="900px", width="100%", directed=True)
net.from_nx(G)

net.set_options(
    """
    {
      "layout": {
        "improvedLayout": true,
        "hierarchical": {
          "enabled": true,
          "direction": "UD",
          "sortMethod": "directed",
          "levelSeparation": 220,
          "nodeSpacing": 220,
          "treeSpacing": 300,
          "blockShifting": true,
          "edgeMinimization": true,
          "parentCentralization": true,
          "shakeTowards": "roots"
        }
      },
      "nodes": {
        "shape": "box",
        "margin": 6,
        "font": {
          "face": "Arial",
          "size": 10
        }
      },
      "edges": {
        "arrows": {
          "to": {
            "enabled": true,
            "scaleFactor": 0.5
          }
        },
        "smooth": {
          "type": "cubicBezier",
          "roundness": 0.5
        }
      },
      "interaction": {
        "dragNodes": true,
        "hideEdgesOnDrag": false,
        "hideNodesOnDrag": false
      },
      "physics": {
        "enabled": true,
        "solver": "hierarchicalRepulsion",
        "hierarchicalRepulsion": {
          "nodeDistance": 280,
          "centralGravity": 0.0,
          "springLength": 220,
          "springConstant": 0.01,
          "damping": 0.15,
          "avoidOverlap": 1
        },
        "stabilization": {
          "iterations": 300
        }
      }
    }
    """
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
net.show(str(OUTPUT_DIR / "zha_mesh.html"), notebook=False)

import xml.etree.ElementTree as ET
import networkx as nx
import os

def load_graphml_custom(filepath):
    """
    自訂 GraphML 讀取函數，解決原生 networkx.read_graphml() 崩潰問題。
    並將字串屬性自動轉換為合適的數值型態（float/int）。
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到檔案：{filepath}")
        
    tree = ET.parse(filepath)
    root = tree.getroot()
    ns = {'g': 'http://graphml.graphdrawing.org/xmlns'}
    
    # 解析 key 定義以對應屬性名稱與資料型態
    keys = {}
    for key_elem in root.findall('g:key', ns):
        k_id = key_elem.get('id')
        k_name = key_elem.get('attr.name')
        k_type = key_elem.get('attr.type')
        k_for = key_elem.get('for')
        keys[k_id] = (k_name, k_type, k_for)
        
    G = nx.MultiDiGraph()
    
    # 獲取圖層範圍屬性
    graph_elem = root.find('g:graph', ns)
    if graph_elem is None:
        raise ValueError("GraphML 中找不到 graph 元素")
        
    # 讀取 CRS 屬性
    crs_data = graph_elem.find("g:data[@key='d0']", ns)
    if crs_data is not None:
        G.graph['crs'] = crs_data.text
        
    # 解析 Nodes (節點)
    for node_elem in graph_elem.findall('g:node', ns):
        node_id = node_elem.get('id')
        node_attrs = {}
        for data_elem in node_elem.findall('g:data', ns):
            k_id = data_elem.get('key')
            if k_id in keys:
                name, type_str, _ = keys[k_id]
                val = data_elem.text
                if val is not None:
                    # 型態轉換
                    if type_str in ('double', 'float'):
                        val = float(val)
                    elif type_str in ('int', 'integer'):
                        val = int(val)
                node_attrs[name] = val
                
        # 強制將 x, y 坐標轉換為 float
        for coord in ('x', 'y'):
            if coord in node_attrs and node_attrs[coord] is not None:
                node_attrs[coord] = float(node_attrs[coord])
                
        G.add_node(node_id, **node_attrs)
        
    # 解析 Edges (路段)
    for edge_elem in graph_elem.findall('g:edge', ns):
        source = edge_elem.get('source')
        target = edge_elem.get('target')
        edge_id = edge_elem.get('id')
        edge_attrs = {}
        for data_elem in edge_elem.findall('g:data', ns):
            k_id = data_elem.get('key')
            if k_id in keys:
                name, type_str, _ = keys[k_id]
                val = data_elem.text
                if val is not None:
                    # 型態轉換
                    if type_str in ('double', 'float'):
                        val = float(val)
                    elif type_str in ('int', 'integer'):
                        val = int(val)
                edge_attrs[name] = val
                
        # 強制將數值欄位轉為 float
        float_cols = [
            'length', 'shading_index', 'safety_score', 'dynamic_shadow_ratio', 
            'dynamic_wbgt_c', 'dynamic_uv_index', 'dynamic_pm25_kriging', 'dynamic_temperature_c',
            'cost', 'unit_cost', 'cost_balanced', 'unit_cost_balanced',
            'cost_heat_averse', 'unit_cost_heat_averse', 'cost_safety_first', 'unit_cost_safety_first'
        ]
        for col in float_cols:
            if col in edge_attrs and edge_attrs[col] is not None:
                try:
                    edge_attrs[col] = float(edge_attrs[col])
                except ValueError:
                    pass
                    
        # 邊的唯一 Key 預設為 0
        key_val = int(edge_id) if edge_id is not None and edge_id.isdigit() else 0
        G.add_edge(source, target, key=key_val, **edge_attrs)
        
    return G

def write_graphml_custom(G, filepath):
    """
    自訂 GraphML 寫入函數，避免 networkx.write_graphml() 崩潰問題。
    """
    root = ET.Element("graphml", {
        "xmlns": "http://graphml.graphdrawing.org/xmlns",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": "http://graphml.graphdrawing.org/xmlns http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd"
    })
    
    # 預定義所有可能屬性的屬性欄位，確保標準且一致的 GraphML 結構
    keys_def = [
        ('d0', 'graph', 'crs', 'string'),
        ('d1', 'node', 'y', 'double'),
        ('d2', 'node', 'x', 'double'),
        ('d3', 'node', 'street_count', 'string'),
        ('d4', 'node', 'highway', 'string'),
        ('d5', 'node', 'railway', 'string'),
        ('d6', 'node', 'ref', 'string'),
        ('d7', 'edge', 'osmid', 'string'),
        ('d8', 'edge', 'name', 'string'),
        ('d9', 'edge', 'length', 'double'),
        ('d10', 'edge', 'shading_index', 'double'),
        ('d11', 'edge', 'safety_score', 'double'),
        ('d12', 'edge', 'dynamic_shadow_ratio', 'double'),
        ('d13', 'edge', 'dynamic_wbgt_c', 'double'),
        ('d14', 'edge', 'dynamic_temperature_c', 'double'),
        ('d15', 'edge', 'dynamic_uv_index', 'double'),
        ('d16', 'edge', 'dynamic_pm25_kriging', 'double'),
        ('d17', 'edge', 'geometry', 'string'),
        ('d18', 'edge', 'cost', 'double'),
        ('d19', 'edge', 'unit_cost', 'double'),
        ('d20', 'edge', 'cost_balanced', 'double'),
        ('d21', 'edge', 'unit_cost_balanced', 'double'),
        ('d22', 'edge', 'cost_heat_averse', 'double'),
        ('d23', 'edge', 'unit_cost_heat_averse', 'double'),
        ('d24', 'edge', 'cost_safety_first', 'double'),
        ('d25', 'edge', 'unit_cost_safety_first', 'double'),
    ]
    
    for k_id, k_for, k_name, k_type in keys_def:
        ET.SubElement(root, "key", {
            "id": k_id,
            "for": k_for,
            "attr.name": k_name,
            "attr.type": k_type
        })
        
    # 建立名稱到 key id 的映射
    node_key_map = {'y': 'd1', 'x': 'd2', 'street_count': 'd3', 'highway': 'd4', 'railway': 'd5', 'ref': 'd6'}
    edge_key_map = {
        'osmid': 'd7', 'name': 'd8', 'length': 'd9', 'shading_index': 'd10', 'safety_score': 'd11',
        'dynamic_shadow_ratio': 'd12', 'dynamic_wbgt_c': 'd13', 'dynamic_temperature_c': 'd14',
        'dynamic_uv_index': 'd15', 'dynamic_pm25_kriging': 'd16', 'geometry': 'd17',
        'cost': 'd18', 'unit_cost': 'd19',
        'cost_balanced': 'd20', 'unit_cost_balanced': 'd21',
        'cost_heat_averse': 'd22', 'unit_cost_heat_averse': 'd23',
        'cost_safety_first': 'd24', 'unit_cost_safety_first': 'd25'
    }
    
    graph_elem = ET.SubElement(root, "graph", {
        "id": "G",
        "edgedefault": "directed"
    })
    
    # 寫入 CRS 屬性
    if 'crs' in G.graph and G.graph['crs'] is not None:
        data_elem = ET.SubElement(graph_elem, "data", {"key": "d0"})
        data_elem.text = str(G.graph['crs'])
        
    # 寫入 Nodes
    for node_id, attrs in G.nodes(data=True):
        node_elem = ET.SubElement(graph_elem, "node", {"id": str(node_id)})
        for attr_name, attr_val in attrs.items():
            if attr_name in node_key_map and attr_val is not None:
                data_elem = ET.SubElement(node_elem, "data", {"key": node_key_map[attr_name]})
                data_elem.text = str(attr_val)
                
    # 寫入 Edges
    for u, v, key, attrs in G.edges(keys=True, data=True):
        edge_elem = ET.SubElement(graph_elem, "edge", {
            "source": str(u),
            "target": str(v),
            "id": str(key)
        })
        for attr_name, attr_val in attrs.items():
            if attr_name in edge_key_map and attr_val is not None:
                data_elem = ET.SubElement(edge_elem, "data", {"key": edge_key_map[attr_name]})
                data_elem.text = str(attr_val)
                
    # 確保輸出目錄存在
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    
    # 寫入 XML 檔案
    tree = ET.ElementTree(root)
    tree.write(filepath, encoding="utf-8", xml_declaration=True)

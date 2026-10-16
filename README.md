# **PanchanScope**

## **Introduction**
PanchanScope is an open-source tool designed to **identify and map Panchan malware relay networks**. This project is for **educational purposes only**, created to analyze malicious infrastructures used by the Panchan malware. **The tool is not intended for malicious or illegal use.**

I am not a professional cybersecurity expert but someone who is passionate about cybersecurity and enjoys exploring malware mechanisms. This project represents my curiosity and desire to learn while sharing knowledge with the community.

> PanchanScope is the evolution of ChanGather: same goal, with multi-threaded crawling, geolocation/ASN enrichment, AS classification and an interactive live map.

---

## **Main Features**
- **Recursive Relay Mapping**: Discovers other relays from one or more seed IPs and a port, recursively mapping the Panchan network.
- **Multi-Threaded Crawling**: A pool of worker threads probes many relays in parallel, so large networks are mapped in minutes instead of hours.
- **Discovery Tree**: Prints a clean tree of the seed, the relays it announces, and the relays found from those — each marked `alive` / `dead` / `pending`.
- **Geo / ASN Enrichment**: Enriches every discovered IP with country, city, coordinates, ISP, org and AS number (via ip-api.com, no API key required).
- **AS Classification**: Groups relays by their Autonomous System, so you can see which operators host the network and how it clusters.
- **Live Web Map**: A built-in web server renders a real-time map in the browser — discovery tree, interactive graph, AS grouping, hub highlighting and per-node details.
- **Exports**: Saves the result as a Graphviz DOT graph or a structured JSON dump (including AS groups), or exports directly from the web view.
- **Offline Schema**: A companion script, `json2schema.py`, turns any JSON export into a standalone interactive HTML map — no server needed.

---

## **Prerequisites**
Before using PanchanScope, ensure you have the following:

### **Required Software**
- **Python 3.8+**

### **Python Modules**
PanchanScope uses mostly standard library modules (`re`, `socket`, `ipaddress`, `argparse`, `threading`, `queue`, `json`, `urllib`, `http.server`), plus one external dependency for nicer logging:
- `loguru`

Install it with:
```bash
> pip install -r requirements.txt
```

### **Optional**
- [Graphviz](https://graphviz.org/) (`dot`) — only needed to render a DOT export into a PNG/SVG image. The web view and `json2schema.py` do **not** require it.

---

## **Installation**
1. Clone the repository from GitHub:
   ```bash
   > git clone https://github.com/redrabytes/changather.git
   > cd changather
   ```

2. Install the dependency:
   ```bash
   > pip install -r requirements.txt
   ```

3. Make the script executable:
   ```bash
   > chmod +x panchanscope.py
   ```

---

## **Usage**
### **Command**
PanchanScope now uses a flag-based command line:
```bash
> ./panchanscope.py [host] [options]
```

### **Parameters**
- `host`: IP of a seed node to start from.
- `-f, --file`: Text file with one seed IP per line (combine with or instead of `host`).
- `-p, --port`: Panchan socket port (default: `1919`).
- `-t, --timeout`: Socket timeout in seconds (default: `5`).
- `-m, --max-nodes`: Maximum number of nodes to contact (anti-runaway safety).
- `-T, --workers`: Number of parallel crawler threads (default: `20`).
- `-o, --output`: Write a Graphviz DOT file of the graph.
- `-j, --json`: Dump enriched node data to a JSON file.
- `--no-enrich`: Skip the geo/ASN enrichment step.
- `-w, --web`: Serve the live tree + graph in the browser.
- `--web-host` / `--web-port`: Bind address / port for the live view (default: `0.0.0.0:8080`).

### **Examples**
```bash
# Crawl from a single seed and print the discovery tree
> ./panchanscope.py 192.168.1.100

# Crawl from a list of seeds with 30 workers and serve the live web map
> ./panchanscope.py -f seeds.txt -T 30 -w
#   then open http://<host>:8080 in a browser

# Crawl, then export both a DOT graph and a JSON dump
> ./panchanscope.py -f seeds.txt -o network.dot -j network.json

# Build a standalone interactive HTML map from a JSON export (no server, no Graphviz)
> ./json2schema.py network.json -o schema.html
```

### **Output**
- **Real-Time Logs**: Displays discovered relays live, plus the live web map when `-w` is used.
- **Discovery Tree**: A terminal tree of the mapped network, with status and AS per node.
- **Final Statistics**: Total nodes contacted, alive nodes, and edges discovered.
- **Exports**: DOT / JSON files, or browser exports from the live view.

> **Security note:** with `-w`, the web server listens on `0.0.0.0` by default. On a public server, restrict the port with your firewall, or bind to localhost (`--web-host 127.0.0.1`) and reach it through an SSH tunnel (`ssh -L 8080:127.0.0.1:8080 user@your-server`).

---

## **How It Works**
1. **Initial Connection**: The tool connects to each IP on the Panchan socket (`1919/tcp` by default) using a TCP socket, across a pool of worker threads.
2. **Data Analysis**: If the response contains the keyword `pan-chan`, the tool extracts all IP addresses from the response.
3. **Recursive Discovery**: New IPs are queued and recursively explored, building the discovery tree and the interconnection graph of the relay network.
4. **Enrichment & Classification**: Discovered IPs are enriched with geolocation and ASN data, then grouped by Autonomous System.
5. **Visualization & Output**: Results are shown in the terminal tree and the live web map, and can be exported to DOT / JSON.
6. **Completion**: The scan finishes when the queue is empty, and a summary of discovered relays is provided.

---

## **Disclaimer**
PanchanScope is designed **for educational and research purposes only**. I am not responsible for any misuse or illegal activities conducted with this tool. Always ensure compliance with your local laws regarding network analysis and cybersecurity research.

---

## **Contributions**
I am open to feedback and contributions to improve this project. Since I am not a professional developer, suggestions, bug reports, and pull requests are highly appreciated to make the code more robust and efficient.

---

## **Contact**
If you have any questions or ideas, feel free to reach out to me via GitHub or Twitter.

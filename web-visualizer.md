# Web Visualizer Template

## logic
The visualizer uses **Mermaid.js** via CDN to render the `hardware_map.json` into a block diagram.

## HTML Structure
```html
<!DOCTYPE html>
<html>
<head>
    <script src="[https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js](https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js)"></script>
    <script>mermaid.initialize({startOnLoad:true});</script>
</head>
<body>
    <h1>Hardware Block Diagram</h1>
    <div class="mermaid">
        %% MERMAID_INSERTION_POINT %%
    </div>
</body>
</html>

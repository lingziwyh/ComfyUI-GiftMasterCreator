import { app } from "/scripts/app.js";

const EXECUTOR_NODE = "GiftMaster_APISkillExecutor";
const FIRST_IMAGE = 1;
const LAST_IMAGE = 9;
const IMAGE_INPUT_PATTERN = /^image_([1-9])$/;

// Workflow loading creates nodes before their saved links have been restored.
// Keep every backend-declared image socket until after graph configuration so
// a connected socket from an older workflow can never be removed prematurely.
let configuringGraph = false;

function imageInputName(index) {
    return `image_${index}`;
}

function imageInputLabel(index) {
    return `参考图 ${index}`;
}

function getImageIndex(input) {
    const match = IMAGE_INPUT_PATTERN.exec(input?.name ?? "");
    return match ? Number(match[1]) : null;
}

function isConnected(input) {
    return input?.link !== null && input?.link !== undefined;
}

function isExecutorNode(node) {
    return node?.comfyClass === EXECUTOR_NODE || node?.type === EXECUTOR_NODE;
}

function graphAndSubgraphNodes(rootGraph) {
    const nodes = [];
    const pending = [rootGraph];
    const visited = new Set();

    while (pending.length) {
        const candidate = pending.pop();
        const graph = candidate?._nodes ? candidate : candidate?.graph;
        if (!graph || visited.has(graph)) continue;
        visited.add(graph);

        for (const node of graph._nodes ?? []) {
            nodes.push(node);
            if (node?.subgraph) pending.push(node.subgraph);
        }

        const subgraphs = graph.subgraphs;
        if (typeof subgraphs?.values === "function") {
            pending.push(...subgraphs.values());
        } else if (Array.isArray(subgraphs)) {
            pending.push(...subgraphs);
        } else if (subgraphs && typeof subgraphs === "object") {
            pending.push(...Object.values(subgraphs));
        }
    }

    return nodes;
}

function localizeImageInputs(node) {
    for (const input of node.inputs ?? []) {
        const index = getImageIndex(input);
        if (index === null) continue;

        // `name` is the canonical API key and must not be translated.
        const label = imageInputLabel(index);
        input.label = label;
        input.localized_name = label;
    }
}

function refreshNodeSize(node) {
    const computed = node.computeSize?.();
    if (computed?.length >= 2 && node.setSize) {
        const currentWidth = Number(node.size?.[0]) || 0;
        node.setSize([Math.max(currentWidth, computed[0]), computed[1]]);
    }
    node.setDirtyCanvas?.(true, true);
}

function syncImageInputs(node) {
    if (!isExecutorNode(node) || node.__giftMasterSyncingImages) return;

    node.__giftMasterSyncingImages = true;
    try {
        const imageInputs = (node.inputs ?? []).filter((input) => getImageIndex(input) !== null);
        const highestConnected = imageInputs.reduce((highest, input) => {
            const index = getImageIndex(input);
            return isConnected(input) ? Math.max(highest, index) : highest;
        }, 0);
        const visibleThrough = Math.min(LAST_IMAGE, Math.max(FIRST_IMAGE, highestConnected + 1));

        // Restore any missing canonical sockets without reordering existing
        // sockets; reordering could invalidate slot-based links in old graphs.
        for (let index = FIRST_IMAGE; index <= visibleThrough; index += 1) {
            const name = imageInputName(index);
            if (!(node.inputs ?? []).some((input) => input.name === name)) {
                node.addInput(name, "IMAGE");
            }
        }

        // Only remove unlinked image sockets beyond the useful trailing empty
        // socket. A connected socket is preserved regardless of its number.
        for (let index = LAST_IMAGE; index > visibleThrough; index -= 1) {
            const slot = (node.inputs ?? []).findIndex((input) => input.name === imageInputName(index));
            if (slot >= 0 && !isConnected(node.inputs[slot])) {
                node.removeInput(slot);
            }
        }

        localizeImageInputs(node);
        refreshNodeSize(node);
    } finally {
        node.__giftMasterSyncingImages = false;
    }
}

function queueImageSync(node) {
    if (node.__giftMasterImageSyncQueued) return;
    node.__giftMasterImageSyncQueued = true;

    queueMicrotask(() => {
        node.__giftMasterImageSyncQueued = false;
        if (!configuringGraph) syncImageInputs(node);
    });
}

app.registerExtension({
    name: "GiftMasterCreator.DynamicImageInputs",

    beforeConfigureGraph() {
        configuringGraph = true;
    },

    afterConfigureGraph() {
        try {
            for (const node of graphAndSubgraphNodes(app.graph)) {
                if (isExecutorNode(node)) syncImageInputs(node);
            }
        } finally {
            configuringGraph = false;
        }
    },

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name !== EXECUTOR_NODE || nodeType.prototype.__giftMasterDynamicImages) return;

        Object.defineProperty(nodeType.prototype, "__giftMasterDynamicImages", {
            value: true,
            configurable: false,
        });

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);
            localizeImageInputs(this);
            if (!configuringGraph) queueImageSync(this);
            return result;
        };

        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const result = onConnectionsChange?.apply(this, arguments);
            if (!configuringGraph) queueImageSync(this);
            return result;
        };
    },
});

import { ContextView } from './components/ContextView.js';
import { EventView } from './components/EventView.js';
import { ToolView } from './components/ToolView.js';

const app = Vue.createApp({
    components: {
        ContextView,
        EventView,
        ToolView
    },
    data() {
        return {
            tools: new Map(),
            contextsAll: new Map(),
            ws: null,
            retryCount: 0,
            settings: {
                expandedByDefault: localStorage.getItem('expandedByDefault') === 'true' || true,
                viewMode: localStorage.getItem('viewMode') || 'separate'
            },
            wsStatus: 'disconnected',
            searchQuery: '',
            isExpanded: true,
            wsHost: localStorage.getItem('wsHost') || 'localhost',
            wsPort: parseInt(localStorage.getItem('wsPort')) || 9001,
            showSettings: false,
            autoReconnect: localStorage.getItem('autoReconnect') !== 'false',
            showTools: false,
            toolEmojis: [
                '&#9986;',   // Scissors
                '&#128295;', // Wrench
                '&#128301;', // Telescope
                '&#128300;', // Microscope
                '&#128736;', // Hammer and Wrench
                '&#9874;',   // Hammer and Pick
                '&#129520;'  // Toolbox
            ],
            currentToolEmoji: '&#128296;',
            isDarkMode: localStorage.getItem('darkMode') === 'true' || false,
            selectedTool: null,
        }
    },
    watch: {
        'settings.viewMode'(newValue) {
            localStorage.setItem('viewMode', newValue);
        },
        'settings.expandedByDefault'(newValue) {
            localStorage.setItem('expandedByDefault', newValue);
        },
        wsHost(newValue) {
            localStorage.setItem('wsHost', newValue);
        },
        wsPort(newValue) {
            localStorage.setItem('wsPort', newValue);
        },
        autoReconnect(newValue) {
            localStorage.setItem('autoReconnect', newValue);
        },
        isDarkMode(newValue) {
            localStorage.setItem('darkMode', newValue);
        }
    },
    computed: {
        connectionClass() {
            return {
                'connection-connected': this.wsStatus === 'connected',
                'connection-disconnected': this.wsStatus === 'disconnected',
                'connection-error': this.wsStatus === 'error'
            };
        },
        connectionStatus() {
            return this.wsStatus.charAt(0).toUpperCase() + this.wsStatus.slice(1);
        },
        contexts() {
            // Helper function to build the tree for a context
            const buildContextTree = (contextId) => {

                const context = this.contextsAll.get(contextId);
                if (!context) return null;

                // Create a new object with all properties
                const contextWithChildren = { ...context };

                // Find all direct children
                const children = Array.from(this.contextsAll.values())
                    .filter(c => c.parent_id === contextId);

                // Recursively build tree for each child
                contextWithChildren.children = children
                    .map(child => buildContextTree(child.id))
                    .filter(child => child !== null);

                return contextWithChildren;
            };

            // Find all root contexts (those without parent_id)
            const rootContexts = Array.from(this.contextsAll.values())
                .filter(context => !context.parent_id);

            // Build the complete tree for each root context
            const contextMap = new Map();
            rootContexts.forEach(rootContext => {
                const tree = buildContextTree(rootContext.id);
                if (tree) {
                    contextMap.set(rootContext.id, tree);
                }
            });

            return contextMap;
        },
        // Sort tools alphabetically by name
        sortedTools() {
            return Array.from(this.tools.values())
                .sort((a, b) => a.name.localeCompare(b.name));
        }
    },
    methods: {
        formatTimestamp(timestamp) {
            if (!timestamp) return '';
            const date = new Date(timestamp * 1000);
            return date.toLocaleTimeString();
        },
        handleTool(data) {
            let toolData = data.data || data;
            this.tools.set(toolData.id, toolData);
        },
        handleContext(contextData) {
            const context = {
                id: contextData.id,
                parent_id: contextData.parent_id,
                root_id: contextData.root_id,
                tool_id: contextData.tool_id,
                tool_name: contextData.tool_name,
                status: contextData.status,
                args: contextData.args,
                output: contextData.output,
                error: contextData.error,
                created_at: contextData.created_at,
                events: contextData.history || [],
                children: [],
            };

            this.contextsAll.set(context.id, context);

            for (const child of contextData.children) {
                this.handleContext(child);
            }

            // Force reactivity
            this.contextsAll = new Map(this.contextsAll);
        },
        handleEvent(data) {
            const contextId = data.context_id;
            const eventData = data.data;

            // Find the context in either map
            const context = this.contextsAll.get(contextId);
            if (!context) {
                console.warn(`Received event for unknown context ${contextId}`);
                return;
            }

            // Ensure events array exists
            if (!context.events) {
                context.events = [];
            }

            // We don't show update events, we just adopt its change
            if (eventData.type === 'context_update') {
                if (eventData.data.tool_id) {
                    context.tool_id = eventData.data.tool_id;
                }
                if (eventData.data.tool_name) {
                    context.tool_name = eventData.data.tool_name;
                }
                this.contextsAll.set(contextId, { ...context });
                return;
            }

            // Add the event
            context.events.push(eventData);

            // Update context based on event type
            if (eventData.type === 'tool_return') {
                context.output = eventData.data;
                context.status = 'complete';
            } else if (eventData.type === 'tool_exception') {
                context.error = eventData.data;
                context.status = 'error';
            }

            // Force reactivity by updating both maps
            this.contextsAll.set(contextId, { ...context });
        },
        setupWebSocket() {
            try {
                if (this.ws) {
                    this.ws.close();
                    this.ws = null;
                }

                const ws = new WebSocket(`ws://${this.wsHost}:${this.wsPort}`);
                this.ws = ws;

                ws.onopen = () => {
                    this.wsStatus = 'connected';
                    this.retryCount = 0;
                };

                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    console.log("MSG", data);
                    if (data.type === 'context') {
                        this.handleContext(data.data);
                    } else if (data.type === 'event') {
                        this.handleEvent(data);
                    } else if (data.type === 'tool') {
                        this.handleTool(data);
                    }
                };

                ws.onclose = () => {
                    console.log('WebSocket disconnected');
                    this.wsStatus = 'disconnected';
                    this.ws = null;

                    if (this.autoReconnect && this.retryCount < 5) {
                        this.retryCount++;
                        setTimeout(() => this.setupWebSocket(), 1000 * this.retryCount);
                    }
                };

                ws.onerror = (error) => {
                    console.error('WebSocket error:', error);
                    this.wsStatus = 'error';
                };

            } catch (error) {
                console.error('Failed to connect:', error);
                this.wsStatus = 'disconnected';
                if (this.autoReconnect) {
                    setTimeout(() => this.setupWebSocket(), 1000);
                }
            }
        },
        reconnectWebSocket() {
            this.autoReconnect = true;
            this.retryCount = 0;
            this.wsStatus = 'connecting';
            this.setupWebSocket();
        },
        disconnectWebSocket() {
            this.autoReconnect = false;
            if (this.ws) {
                this.ws.close();
                this.ws = null;
            }
            this.wsStatus = 'disconnected';
        },
        randomizeToolEmoji() {
            const randomIndex = Math.floor(Math.random() * this.toolEmojis.length);
            this.currentToolEmoji = this.toolEmojis[randomIndex];
        },
        toggleTheme() {
            this.isDarkMode = !this.isDarkMode;
            document.documentElement.classList.toggle('dark-mode', this.isDarkMode);
        },
        selectTool(tool) {
            this.selectedTool = tool;
        },
        clearSelectedTool() {
            this.selectedTool = null;
        }
    },
    mounted() {
        this.setupWebSocket();
        document.documentElement.classList.toggle('dark-mode', this.isDarkMode);
    }
});

app.mount('#app'); 
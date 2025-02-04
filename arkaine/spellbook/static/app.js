import { ContextView } from './components/ContextView.js';
import { EventView } from './components/EventView.js';
import { LLMView } from './components/LLMView.js';
import { ToolView } from './components/ToolView.js';

const app = Vue.createApp({
    components: {
        'context-view': ContextView,
        'event-view': EventView,
        'tool-view': ToolView,
        'llm-view': LLMView
    },
    data() {
        return {
            producers: new Map(),
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
            selectedProducer: null,
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
        sortedProducers() {
            const sorted = {};

            for (const [type, producersMap] of this.producers) {
                const sortedProducers = Array.from(producersMap.values())
                    .sort((a, b) => a.name.localeCompare(b.name));
                sorted[type] = sortedProducers;
            }

            return sorted;
        },
    },
    methods: {
        formatTimestamp(timestamp) {
            if (!timestamp) return '';
            const date = new Date(timestamp * 1000);
            return date.toLocaleTimeString();
        },
        handleProducer(data) {
            const producerData = data.data || data;

            // If this producer type doesn't exist in the Map, create a new Map for it
            if (!this.producers.has(producerData.type)) {
                this.producers.set(producerData.type, new Map());
            }

            // Get the type's Map and set the producer
            const typeMap = this.producers.get(producerData.type);
            typeMap.set(producerData.id, producerData);

            // Force Vue reactivity by creating a new Map
            this.producers = new Map(this.producers);
        },
        handleContext(contextData) {
            let data = {}
            if (contextData.data && "data" in contextData.data) {
                data = contextData.data.data;
            }

            let data_x = {}
            if (contextData.x && "data" in contextData.x) {
                data_x = contextData.x.data;
            }

            let data_debug = {}
            if (contextData.debug && "data" in contextData.debug) {
                data_debug = contextData.debug.data;
            }

            const context = {
                id: contextData.id,
                parent_id: contextData.parent_id,
                root_id: contextData.root_id,
                attached_id: contextData.attached_id,
                attached_type: contextData.attached_type,
                attached_name: contextData.attached_name,
                status: contextData.status,
                args: contextData.args,
                output: contextData.output,
                error: contextData.error,
                created_at: contextData.created_at,
                events: contextData.history || [],
                children: [],
                data: data,
                x: data_x,
                debug: data_debug
            };

            // Log for debugging
            console.log("Handling context with data:", contextData);

            this.contextsAll.set(context.id, context);

            // Handle any child contexts
            if (contextData.children) {
                for (const child of contextData.children) {
                    this.handleContext(child);
                }
            }

            // Force reactivity by creating a new Map
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
                if (eventData.data.attached_id) {
                    context.attached_id = eventData.data.attached_id;
                }
                if (eventData.data.attached_name) {
                    context.attached_name = eventData.data.attached_name;
                }
                if (eventData.data.attached_type) {
                    context.attached_type = eventData.data.attached_type;
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
            } else if (eventData.type == "llm_response") {
                context.output = eventData.data;
                context.status = 'complete';
            }

            // Force reactivity by updating both maps
            this.contextsAll.set(contextId, { ...context });
        },
        handleDataStore(data) {
            const contextId = data.data.context;  // Note: Changed from data.context to data.data.context
            const label = data.data.label;        // Changed from data.label to data.data.label
            const dataStore = data.data.data;     // Changed to get the actual data

            console.log("Handling datastore update:", { contextId, label, dataStore });

            const context = this.contextsAll.get(contextId);
            if (!context) {
                console.warn(`Received data store for unknown context ${contextId}`);
                return;
            }

            // Update the appropriate data store based on label
            if (label === 'data') {
                context.data = dataStore;
            } else if (label === 'x') {
                context.x = dataStore;
            } else if (label === 'debug') {
                context.debug = dataStore;
            } else {
                console.warn(`Received data store for unknown label ${label} in context ${contextId}`);
                return;
            }

            // Force Vue to recognize the change
            this.contextsAll.set(contextId, { ...context });
        },
        handleDataStoreUpdate(data) {
            const contextId = data.data.context;  // Changed from data.context
            const label = data.data.label;        // Changed from data.label
            const key = data.data.key;            // Changed from data.key
            const value = data.data.value;        // Changed from data.value

            console.log("Handling datastore update:", { contextId, label, key, value });

            const context = this.contextsAll.get(contextId);
            if (!context) {
                console.warn(`Received data store update for unknown context ${contextId}`);
                return;
            }

            // Update the appropriate data store based on label
            if (label === 'data') {
                context.data[key] = value;
            } else if (label === 'x') {
                context.x[key] = value;
            } else if (label === 'debug') {
                context.debug[key] = value;
            } else {
                console.warn(`Received data store update for unknown label ${label} in context ${contextId}`);
                return;
            }

            // Force Vue to recognize the change
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
                    } else if (data.type === 'producer') {
                        this.handleProducer(data);
                    } else if (data.type === 'datastore') {
                        this.handleDataStore(data);
                    } else if (data.type === 'datastore_update') {
                        this.handleDataStoreUpdate(data);
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
        selectProducer(producer) {
            this.selectedProducer = producer;
        },
        clearSelectedProducer() {
            this.selectedProducer = null;
        },
        executeProducer(data) {
            if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
                console.error('WebSocket is not connected');
                return;
            }

            const message = {
                type: 'execution',
                producer_id: data.attached_id,
                producer_type: data.attached_type,
                args: data.args
            };

            this.ws.send(JSON.stringify(message));
        },
        handleOutsideClick(event) {
            // Close tools panel if click is outside
            if (this.showTools && !event.target.closest('.tools-panel') &&
                !event.target.closest('.global-tools-button')) {
                this.showTools = false;
            }

            // Close settings panel if click is outside
            if (this.showSettings && !event.target.closest('.floating-settings-panel') &&
                !event.target.closest('.global-settings-button')) {
                this.showSettings = false;
            }
        },
        handleContextRetry(contextId) {
            // Prepare our message
            const message = {
                type: "context_retry",
                context_id: contextId
            }

            // Clear the context entirely from our app memory
            this.contextsAll.delete(contextId);

            // Finally send the message
            this.ws.send(JSON.stringify(message));
        }
    },
    mounted() {
        this.setupWebSocket();
        document.documentElement.classList.toggle('dark-mode', this.isDarkMode);
        // Add click event listener to document
        document.addEventListener('click', this.handleOutsideClick);
    },
    beforeUnmount() {
        // Remove event listener when component is destroyed
        document.removeEventListener('click', this.handleOutsideClick);
    }
});

app.mount('#app'); 
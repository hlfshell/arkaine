import { ContextView } from './components/ContextView.js';
import { EventView } from './components/EventView.js';

const app = Vue.createApp({
    components: {
        ContextView,
        EventView
    },
    data() {
        return {
            // contexts are only root contexts and is what is displayed
            // contextsAll is a quick reference to prevent having to search
            // through the network of contexts for referencing,
            contextsAll: new Map(),
            ws: null,
            retryCount: 0,
            settings: {
                expandedByDefault: true
            },
            wsStatus: 'disconnected',
            searchQuery: '',
            isExpanded: true
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
    },
    methods: {
        formatTimestamp(timestamp) {
            if (!timestamp) return '';
            const date = new Date(timestamp * 1000);
            return date.toLocaleTimeString();
        },
        handleContext(data) {
            let contextData = data.data || data;

            const context = {
                id: contextData.id,
                parent_id: contextData.parent_id,
                root_id: contextData.root_id,
                tool_id: contextData.tool_id,
                tool_name: contextData.tool_name,
                status: contextData.status,
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

            // Add the event
            context.events.push(eventData);

            // Update context based on event type
            if (eventData.type === 'tool_return' || eventData.type === 'agent_return') {
                context.output = eventData.data;
                context.status = 'complete';
            } else if (eventData.type === 'tool_exception') {
                context.error = eventData.data;
                context.status = 'error';
            }

            // Force reactivity by updating both maps
            this.contextsAll.set(contextId, { ...context });
            // if (!context.parent_id) {
            //     this.contexts.set(contextId, { ...context });
            // }
        },
        setupWebSocket() {
            try {
                if (this.ws) {
                    this.ws.close();
                    this.ws = null;
                }

                const ws = new WebSocket('ws://localhost:9001');
                this.ws = ws;

                ws.onopen = () => {
                    console.log('WebSocket connected');
                    this.wsStatus = 'connected';
                    this.retryCount = 0;
                };

                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    if (data.type === 'context') {
                        this.handleContext(data);
                    } else if (data.type === 'event') {
                        this.handleEvent(data);
                    } else if (data.type === 'tool') {
                        // Handle tool registration if needed
                        console.log('Tool registered:', data.data);
                    }
                };

                ws.onclose = () => {
                    console.log('WebSocket disconnected');
                    this.wsStatus = 'disconnected';
                    if (this.retryCount < 5) {
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
                setTimeout(() => this.setupWebSocket(), 1000);
            }
        },
    },
    mounted() {
        this.setupWebSocket();
    }
});

app.mount('#app'); 
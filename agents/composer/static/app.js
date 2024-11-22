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
            contexts: new Map(),
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
        rootContexts() {
            if (!this.contexts) return [];
            return Array.from(this.contexts.values())
                .filter(context => !context.parent_id);
        },
        connectionClass() {
            return {
                'connection-connected': this.wsStatus === 'connected',
                'connection-disconnected': this.wsStatus === 'disconnected',
                'connection-error': this.wsStatus === 'error'
            };
        },
        connectionStatus() {
            return this.wsStatus.charAt(0).toUpperCase() + this.wsStatus.slice(1);
        }
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

            // Store in contextsAll for quick lookup
            this.contextsAll.set(context.id, context);

            // Update parent mapping
            if (context.parent_id) {
                // If it's a sub-context, add to parent's children
                const parentContext = this.contextsAll.get(context.parent_id);
                if (parentContext) {
                    if (!parentContext.children) {
                        parentContext.children = [];
                    }
                    // Remove any existing entry for this child to avoid duplicates
                    parentContext.children = parentContext.children.filter(child => child.id !== context.id);
                    parentContext.children.push(context);

                    // Force update on parent context
                    this.contextsAll.set(context.parent_id, { ...parentContext });
                    if (!parentContext.parent_id) {
                        this.contexts.set(context.parent_id, { ...parentContext });
                    }
                }
            } else {
                // It's a root context
                this.contexts.set(context.id, context);
            }

            // Now iterate over all children to handle/load them
            for (const child of contextData.children) {
                this.handleContext(child);
            }

            // Force reactivity
            this.contexts = new Map(this.contexts);
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
            if (!context.parent_id) {
                this.contexts.set(contextId, { ...context });
            }
            this.contexts = new Map(this.contexts);
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
                    console.log("Message received:", event);
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
import { ContextView } from './components/ContextView.js';
import { EventView } from './components/EventView.js';

const app = Vue.createApp({
    components: {
        ContextView,
        EventView
    },
    data() {
        return {
            contexts: new Map(),
            contextParentMap: new Map(),
            ws: null,
            retryCount: 0,
            settings: {
                expandedByDefault: true
            },
            wsStatus: 'disconnected',
            searchQuery: ''
        }
    },
    computed: {
        rootContexts() {
            return Array.from(this.contexts.values())
                .filter(context => !context.parent_id);
        }
    },
    methods: {
        updateContext(data) {
            const contextData = data.data;
            const context = {
                id: contextData.id,
                parent_id: contextData.parent_id,
                tool: contextData.tool,
                status: contextData.status,
                output: contextData.output,
                error: contextData.error,
                created_at: contextData.created_at,
                events: contextData.history || [],
                children: []
            };

            // Update parent relationships
            if (context.parent_id) {
                this.contextParentMap.set(context.id, context.parent_id);
                const parentContext = this.contexts.get(context.parent_id);
                if (parentContext && !parentContext.children.includes(context.id)) {
                    parentContext.children.push(context.id);
                }
            }

            // Add/update context in our map
            this.contexts.set(context.id, context);
            // Force reactivity
            this.contexts = new Map(this.contexts);
        },
        handleEvent(data) {
            const contextId = data.context_id;
            const eventData = data.data;

            if (!this.contexts.has(contextId)) {
                console.warn(`Received event for unknown context ${contextId}`);
                return;
            }

            const context = this.contexts.get(contextId);
            context.events.push(eventData);

            // Update context based on event type
            if (eventData.type === 'context_update' && eventData.data) {
                Object.entries(eventData.data).forEach(([key, value]) => {
                    if (key in context) {
                        context[key] = value;
                    }
                });
            }

            // Force reactivity
            this.contexts.set(contextId, { ...context });
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
                    const data = JSON.parse(event.data);
                    if (data.type === 'context') {
                        this.updateContext(data);
                    } else if (data.type === 'event') {
                        this.handleEvent(data);
                    }
                };

                // ... rest of WebSocket setup remains the same ...
            } catch (error) {
                console.error('Failed to connect:', error);
                this.wsStatus = 'disconnected';
                setTimeout(() => this.setupWebSocket(), 1000);
            }
        }
    },
    mounted() {
        this.setupWebSocket();
    }
});

app.mount('#app'); 
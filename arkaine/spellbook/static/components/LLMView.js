export const LLMView = {
    name: 'LLMView',
    props: ['llm', 'contexts', 'searchQuery'],
    data() {
        return {
            isDescriptionExpanded: true,
            isExecutionExpanded: true,
            isTriggersExpanded: true,
            executionForm: {
                prompt: ''
            }
        }
    },
    computed: {
        // Get all contexts that used this LLM
        llmContexts() {
            if (!this.contexts) return [];
            let contexts = Array.from(this.contexts.values())
                .filter(context => context.attached_id === this.llm.id && context.attached_type === 'llm')
                .sort((a, b) => (b.created_at || 0) - (a.created_at || 0));

            // Apply search filter if there's a search query
            if (this.searchQuery?.trim()) {
                const query = this.searchQuery.trim().toLowerCase();
                contexts = contexts.filter(context => {
                    // Check args (prompt)
                    const argsStr = context.args ? JSON.stringify(context.args).toLowerCase() : '';
                    if (argsStr.includes(query)) return true;

                    // Check output (response)
                    const outputStr = context.output ? context.output.toLowerCase() : '';
                    if (outputStr.includes(query)) return true;

                    // Check error
                    if (context.error?.toLowerCase().includes(query)) return true;

                    return false;
                });
            }

            return contexts;
        }
    },
    methods: {
        formatTimestamp(timestamp) {
            if (!timestamp) return 'N/A';
            return new Date(timestamp * 1000).toLocaleString();
        },
        handleExecuteLLM() {
            // Emit a simpler event name
            this.$emit('execute', {
                attached_id: this.llm.id,
                attached_type: 'llm',
                args: {
                    prompt: this.executionForm.prompt
                }
            });

            // Clear the form after sending
            this.executionForm.prompt = '';

            // Reset textarea height
            const textarea = document.querySelector('.prompt-textarea');
            if (textarea) {
                textarea.style.height = 'auto';
            }
        },
        adjustTextareaHeight(event) {
            const textarea = event.target;
            textarea.style.height = 'auto';
            textarea.style.height = textarea.scrollHeight + 'px';
        }
    },
    template: `
        <div class="llm-view">
            <button class="back-button" @click="$emit('back')">&larr; Back</button>
            <div class="llm-header">
                <h2 class="llm-title">{{ llm.name }}</h2>
            </div>
            
            <!-- Execute Section -->
            <div class="llm-section execution-section">
                <div class="section-header" @click="isExecutionExpanded = !isExecutionExpanded">
                    <h3>Send Prompt</h3>
                    <span class="expand-icon">{{ isExecutionExpanded ? '−' : '+' }}</span>
                </div>
                <div v-show="isExecutionExpanded" class="section-content">
                    <form @submit.prevent="handleExecuteLLM" class="execution-form">
                        <div class="prompt-field">
                            <textarea
                                v-model="executionForm.prompt"
                                @input="adjustTextareaHeight"
                                @keydown.ctrl.enter.prevent="handleExecuteLLM"
                                class="prompt-textarea"
                                placeholder="Enter your prompt here..."
                                required
                            ></textarea>
                        </div>
                        
                        <div class="execution-actions">
                            <button type="submit" class="execute-button">
                                Send Prompt
                            </button>
                        </div>
                    </form>
                </div>
            </div>

            <!-- Recent Executions Section -->
            <div class="llm-section">
                <div class="section-header" @click="isTriggersExpanded = !isTriggersExpanded">
                    <h3>Recent Executions ({{ llmContexts.length }})</h3>
                    <span class="expand-icon">{{ isTriggersExpanded ? '−' : '+' }}</span>
                </div>
                <div v-show="isTriggersExpanded" class="section-content">
                    <div v-if="llmContexts.length === 0" class="no-executions">
                        No recent executions for this LLM
                    </div>
                    <div v-else class="executions-list">
                        <div v-for="context in llmContexts" :key="context.id" class="execution-card">
                            <div class="execution-header">
                                <span class="execution-timestamp">{{ formatTimestamp(context.created_at) }}</span>
                                <span class="execution-id">Context {{ context.id }}</span>
                                <span :class="['status', 'status-' + context.status]">
                                    {{ context.status }}
                                </span>
                            </div>
                            <div v-if="context.args" class="execution-prompt">
                                <h4>Prompt</h4>
                                <pre>{{ JSON.stringify(context.args, null, 2) }}</pre>
                            </div>
                            <div v-if="context.output" class="execution-response">
                                <h4>Response</h4>
                                <pre>{{ context.output }}</pre>
                            </div>
                            <div v-if="context.error" class="execution-error">
                                <pre>{{ context.error }}</pre>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `
}; 
import { EventView } from './EventView.js'

export const ContextView = {
    name: 'ContextView',
    components: {
        EventView
    },
    props: ['context', 'settings', 'depth', 'contexts'],
    template: `
        <div class="context-container" :style="{ marginLeft: depth * 20 + 'px' }">
            <div class="context-header">
                <span :class="['status', 'status-' + context.status]">{{ context.status }}</span>
                <div class="context-id-section">
                    <button class="collapse-button" @click="isExpanded = !isExpanded">
                        <span class="collapse-icon"><b>{{ isExpanded ? '−' : '+' }}</b></span>
                        <span class="context-id">Context {{ context.id }}</span>
                    </button>
                    <span v-if="context.tool?.name" class="context-name">{{ context.tool.name }}</span>
                    <span class="context-timestamps">
                        Created: {{ formatTimestamp(context.created_at) }}
                    </span>
                </div>
                <button class="copy-button" @click.stop="copyContext">📋</button>
            </div>
            <!-- ... rest of template remains the same ... -->
        </div>
    `,
    // ... rest of component definition remains the same ...
} 
const { ref, onMounted, onUnmounted } = Vue;

export const ChatView = {
    name: 'ChatView',
    props: ['chat'],
    setup(props, { emit }) {
        // Local list of messages currently displayed in the chat
        const messages = ref([]);

        // Track conversations known for this Chat (for demonstration we mock them).
        // In practice, you'd fetch them from your server via WebSocket or an API.
        const conversations = ref([
            {
                id: 'new',
                name: 'New',
                messages: []
            },
        ]);

        // The currently loaded conversation ID. Defaults to "new".
        const currentConversationId = ref('new');

        // userInput holds the next message typed by the user
        const userInput = ref('');

        // onMount, pretend we fetch an updated conversation list from server
        onMounted(() => {
            // If you had a real method in Chat or your server, you might do:
            // fetchConversationList(props.chat.id).then(list => {
            //   conversations.value = list;
            // });

            // Listen for new contexts from the server
            window.addEventListener('chat_message_incoming', handleChatMessageIncoming);
        });

        onUnmounted(() => {
            window.removeEventListener('chat_message_incoming', handleChatMessageIncoming);
        });

        // Helper: current conversation object
        function currentConversationObj() {
            return conversations.value.find(conv => conv.id === currentConversationId.value);
        }

        // Update local messages whenever we switch conversation
        function loadConversation(convId) {
            currentConversationId.value = convId;
            const conv = currentConversationObj();
            messages.value = conv?.messages || [];
        }

        // Start from new (same as calling loadConversation('new')), but also clear userInput
        function startNewConversation() {
            currentConversationId.value = 'new';
            messages.value = [];
            userInput.value = '';
        }

        // Handle user pressing "Send"
        function sendMessage() {
            if (!userInput.value.trim()) return;

            // Add the user message to local chat
            messages.value.push({
                author: {
                    id: 'user',
                    name: 'User',
                    type: 'human'
                },
                content: userInput.value
            });

            // If we are not in "new" conversation, store it in that conversation's array
            if (currentConversationId.value !== 'new') {
                const conv = currentConversationObj();
                if (conv) {
                    conv.messages.push({
                        author: {
                            id: 'user',
                            name: 'User',
                            type: 'human'
                        },
                        content: userInput.value
                    });
                }
            }

            // Emit an event so the parent can call the chat's tool
            emit('send-message', {
                attached_id: props.chat.id,
                attached_type: props.chat.type,
                args: {
                    message: userInput.value,
                }
            });

            userInput.value = '';
        }

        // Listen for the agent's new output when contexts or events come in
        function handleChatMessageIncoming(e) {
            const ctx = e.detail;
            if (ctx.attached_id === props.chat.id) {
                // We'll treat ctx.output as the agent's reply
                if (ctx.output) {
                    // If we are not in "new" conversation, push the message there, too
                    if (currentConversationId.value !== 'new') {
                        const conv = currentConversationObj();
                        if (conv) {
                            conv.messages.push({
                                author: {
                                    id: 'agent',
                                    name: props.chat.name || 'Agent',
                                    type: 'agent'
                                },
                                content: ctx.output
                            });
                        }
                    }

                    messages.value.push({
                        author: {
                            id: 'agent',
                            name: props.chat.name || 'Agent',
                            type: 'agent'
                        },
                        content: ctx.output
                    });
                }
                // If there's an error, also show it
                if (ctx.error) {
                    messages.value.push({
                        author: {
                            id: 'error',
                            name: '(Error)',
                            type: 'error'
                        },
                        content: ctx.error
                    });
                }
            }
        }

        return {
            userInput,
            messages,
            conversations,
            currentConversationId,
            loadConversation,
            startNewConversation,
            sendMessage
        };
    },
    template: `
    <div class="chat-view-container">
        <!-- Left side conversation list -->
        <div class="conversation-list">
            <ul>
                <li
                  v-for="conv in conversations"
                  :key="conv.id"
                  :class="{ active: conv.id === currentConversationId }"
                  @click="conv.id==='new' ? startNewConversation() : loadConversation(conv.id)"
                >
                    {{ conv.name }}
                </li>
            </ul>
        </div>

        <!-- Right side actual chat view -->
        <div class="chat-view">
            <button class="back-button" @click="$emit('back')">&larr; Back</button>
            <h2 class="chat-header">{{ chat.name || 'Chat Agent' }}</h2>

            <!-- The chat messages area -->
            <div class="chat-messages">
                <div
                    v-for="(msg, index) in messages"
                    :key="index"
                    :class="['chat-message', msg.author.type === 'human' ? 'chat-message-user' : 'chat-message-agent']"
                >
                    <div class="chat-sender">{{ msg.author.name }}</div>
                    <div class="chat-content">{{ msg.content }}</div>
                </div>
            </div>

            <!-- Input box -->
            <div class="chat-input-container">
                <textarea
                    class="chat-textarea"
                    v-model="userInput"
                    rows="3"
                    placeholder="Type a message..."
                    @keydown.ctrl.enter.prevent="sendMessage"
                ></textarea>
                <button class="chat-send-button" @click="sendMessage">Send</button>
            </div>
        </div>
    </div>
    `
};
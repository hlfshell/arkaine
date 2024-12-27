import pytest

from arkaine.utils.documents import (
    InMemoryEmbeddingStore,
    chunk_text_by_sentences,
    generate_embedding,
    isolate_sentences,
)


@pytest.fixture
def sample_text():
    return "This is a test sentence. Here is another one! And a third? Finally, the last one."


@pytest.fixture
def sample_paragraphs():
    return """First paragraph with multiple sentences. Another sentence here.

    Second paragraph starts here. It has two sentences.

    Third paragraph is short."""


@pytest.fixture
def mock_embedding_model():
    def mock_generate_embedding(text):
        # Return a fixed-size vector for testing
        return [0.1] * 384  # or whatever size your embeddings are

    return mock_generate_embedding


def test_isolate_sentences(sample_text):
    """Test sentence isolation"""
    sentences = isolate_sentences(sample_text)
    assert len(sentences) == 4
    assert sentences[0] == "This is a test sentence."
    assert sentences[1] == "Here is another one!"
    assert sentences[2] == "And a third?"
    assert sentences[3] == "Finally, the last one."


def test_chunk_text_single_chunk(sample_text):
    """Test text chunking with single chunk"""
    chunks = chunk_text_by_sentences(sample_text, sentences_per=4)
    assert len(chunks) == 1
    assert chunks[0] == sample_text.strip()


def test_chunk_text_multiple_chunks(sample_text):
    """Test text chunking with multiple chunks"""
    chunks = chunk_text_by_sentences(sample_text, sentences_per=2)
    assert len(chunks) == 2
    assert "This is a test sentence. Here is another one!" in chunks[0]


def test_chunk_text_with_overlap(sample_text):
    """Test text chunking with overlap"""
    # With sentences_per=2 and overlap=1, we expect:
    # Chunk 1: [sentence1, sentence2]
    # Chunk 2: [sentence3, sentence4]
    chunks = chunk_text_by_sentences(sample_text, sentences_per=2, overlap=1)

    # We should have 2 chunks
    assert len(chunks) == 2

    # First chunk should contain first two sentences
    assert "This is a test sentence. Here is another one!" == chunks[0].strip()

    # Second chunk should contain last two sentences
    assert "And a third? Finally, the last one." == chunks[1].strip()

    # Test with larger overlap
    chunks = chunk_text_by_sentences(sample_text, sentences_per=3, overlap=2)
    assert len(chunks) == 2

    # Verify the chunks contain the expected sentences
    first_chunk_sentences = isolate_sentences(chunks[0])
    second_chunk_sentences = isolate_sentences(chunks[1])

    # First chunk should have 3 sentences
    assert len(first_chunk_sentences) == 3
    assert first_chunk_sentences == [
        "This is a test sentence.",
        "Here is another one!",
        "And a third?",
    ]

    # Second chunk will have remaining sentences (2 in this case)
    assert len(second_chunk_sentences) == 2
    assert second_chunk_sentences == [
        "And a third?",
        "Finally, the last one.",
    ]

    # Verify overlap - last sentence of first chunk should match
    # first sentence of second chunk
    assert first_chunk_sentences[-1] == second_chunk_sentences[0]


def test_chunk_text_with_paragraphs(sample_paragraphs):
    """Test text chunking with paragraph isolation"""
    chunks = chunk_text_by_sentences(
        sample_paragraphs, sentences_per=2, isolate_paragraphs=True
    )
    assert len(chunks) >= 3  # At least one chunk per paragraph


@pytest.mark.asyncio
async def test_in_memory_embedding_store(mock_embedding_model):
    """Test InMemoryEmbeddingStore functionality with mock embeddings"""
    store = InMemoryEmbeddingStore(mock_embedding_model)
    store.add_text("This is a test document")
    results = store.query("test document", top_n=2)
    assert len(results) <= 2


@pytest.mark.skip(reason="Requires external embedding model")
def test_generate_embedding():
    """Test embedding generation"""
    text = "This is a test document"
    embedding = generate_embedding(text)
    assert isinstance(embedding, list)
    assert all(isinstance(x, float) for x in embedding)


def test_generate_embedding_mock(mock_embedding_model):
    """Test embedding generation using mock model"""
    text = "This is a test document"
    embedding = mock_embedding_model(text)
    assert isinstance(embedding, list)
    assert len(embedding) == 384  # Size we defined in mock
    assert all(isinstance(x, float) for x in embedding)

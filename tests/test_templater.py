import pytest

from arkaine.utils.templater import PromptTemplate


@pytest.fixture
def simple_template():
    return PromptTemplate("Hello {name}!")


@pytest.fixture
def complex_template():
    return PromptTemplate(
        """
    Name: {name}
    Age: {age}
    Location: {location}
    """
    )


def test_template_initialization(simple_template):
    """Test that template variables are correctly identified"""
    assert "name" in simple_template.variables
    assert simple_template.variables["name"] is None


def test_template_variable_setting(simple_template):
    """Test setting template variables"""
    simple_template["name"] = "World"
    assert simple_template["name"] == "World"


def test_template_variable_not_found(simple_template):
    """Test accessing non-existent template variable"""
    with pytest.raises(ValueError):
        simple_template["nonexistent"]


def test_template_render(simple_template):
    """Test template rendering with variables"""
    result = simple_template.render({"name": "World"}, role="user")
    expected = [{"role": "user", "content": "Hello World!"}]
    assert result == expected


def test_template_render_with_multiple_variables(complex_template):
    """Test template rendering with multiple variables"""
    variables = {"name": "John", "age": "30", "location": "New York"}
    result = complex_template.render(variables, role="system")
    expected = [
        {
            "role": "system",
            "content": """
    Name: John
    Age: 30
    Location: New York
    """,
        }
    ]
    assert result == expected


def test_template_load_from_file(tmp_path):
    """Test loading template from file"""
    # Create a temporary file
    file_path = tmp_path / "test_template.txt"
    file_path.write_text("Hello {name}!")

    template = PromptTemplate.from_file(str(file_path))
    assert "name" in template.variables

    result = template.render({"name": "World"}, role="user")
    expected = [{"role": "user", "content": "Hello World!"}]
    assert result == expected


def test_template_load_json(tmp_path):
    """Test loading JSON template"""
    # Create a temporary JSON file
    file_path = tmp_path / "test_template.json"
    file_path.write_text('{"test": "Hello {name}!"}')

    template = PromptTemplate.from_file(str(file_path))
    assert "name" in template.variables

    result = template.render({"name": "World"}, role="user")
    expected = [{"role": "user", "content": "Hello World!"}]
    assert result == expected

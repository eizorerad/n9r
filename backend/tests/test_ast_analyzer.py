"""Tests for AST-based code analyzer."""

import pytest
from app.services.ast_analyzer import ASTAnalyzer, get_ast_analyzer, TREE_SITTER_AVAILABLE


class TestASTAnalyzer:
    """Test AST analyzer functionality."""
    
    def setup_method(self):
        self.analyzer = ASTAnalyzer()
    
    def test_python_function_params_not_flagged(self):
        """Function parameters should NOT be flagged as generic names."""
        code = '''
def process_user(data, info, result):
    """Process user data."""
    user_name = data["name"]
    return user_name
'''
        result = self.analyzer.analyze_file("test.py", code)
        
        # 'data', 'info', 'result' are params - should NOT be flagged
        flagged_names = [issue.name for issue in result.generic_names]
        assert 'data' not in flagged_names
        assert 'info' not in flagged_names
        assert 'result' not in flagged_names
    
    def test_python_loop_vars_not_flagged(self):
        """Loop variables should NOT be flagged."""
        code = '''
for i in range(10):
    print(i)

for item in items:
    process(item)

for x, y in coordinates:
    draw(x, y)
'''
        result = self.analyzer.analyze_file("test.py", code)
        
        flagged_names = [issue.name for issue in result.generic_names]
        # Loop vars should not be flagged
        assert 'i' not in flagged_names
        assert 'item' not in flagged_names
        assert 'x' not in flagged_names
        assert 'y' not in flagged_names
    
    def test_python_generic_assignment_flagged(self):
        """Generic names in regular assignments SHOULD be flagged."""
        code = '''
def calculate():
    data = fetch_from_api()  # This should be flagged
    result = process(data)   # This should be flagged
    return result
'''
        result = self.analyzer.analyze_file("test.py", code)
        
        flagged_names = [issue.name for issue in result.generic_names]
        # These are actual assignments, should be flagged
        assert 'data' in flagged_names
        assert 'result' in flagged_names
    
    def test_python_comprehension_vars_not_flagged(self):
        """Comprehension variables should NOT be flagged."""
        code = '''
items = [item for item in source]
values = {x: y for x, y in pairs}
'''
        result = self.analyzer.analyze_file("test.py", code)
        
        # Comprehension vars should not be flagged
        flagged_names = [issue.name for issue in result.generic_names]
        # Note: 'items' and 'values' are the assignment targets, not 'item', 'x', 'y'
        assert 'item' not in flagged_names
        assert 'x' not in flagged_names
        assert 'y' not in flagged_names
    
    def test_python_magic_numbers_flagged(self):
        """Magic numbers should be flagged."""
        code = '''
def calculate():
    timeout = 3600  # Magic number
    return value * 42  # Magic number
'''
        result = self.analyzer.analyze_file("test.py", code)
        
        magic_values = [issue.value for issue in result.magic_numbers]
        assert '3600' in magic_values or '42' in magic_values
    
    def test_python_constants_not_flagged(self):
        """UPPER_CASE constants should NOT be flagged as magic numbers."""
        code = '''
TIMEOUT_SECONDS = 3600
MAX_RETRIES = 5
'''
        result = self.analyzer.analyze_file("test.py", code)
        
        # Constants should not be flagged
        magic_values = [issue.value for issue in result.magic_numbers]
        assert '3600' not in magic_values
        assert '5' not in magic_values
    
    def test_common_numbers_not_flagged(self):
        """Common acceptable numbers should NOT be flagged."""
        code = '''
x = 0
y = 1
z = 100
status = 200
'''
        result = self.analyzer.analyze_file("test.py", code)
        
        magic_values = [issue.value for issue in result.magic_numbers]
        assert '0' not in magic_values
        assert '1' not in magic_values
        assert '100' not in magic_values
        assert '200' not in magic_values
    
    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_javascript_function_params_not_flagged(self):
        """JS function parameters should NOT be flagged."""
        code = '''
function processData(data, info) {
    const userName = data.name;
    return userName;
}
'''
        result = self.analyzer.analyze_file("test.js", code)
        
        flagged_names = [issue.name for issue in result.generic_names]
        assert 'data' not in flagged_names
        assert 'info' not in flagged_names
    
    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
    def test_javascript_loop_vars_not_flagged(self):
        """JS loop variables should NOT be flagged."""
        code = '''
for (let i = 0; i < 10; i++) {
    console.log(i);
}

for (const item of items) {
    process(item);
}
'''
        result = self.analyzer.analyze_file("test.js", code)
        
        flagged_names = [issue.name for issue in result.generic_names]
        assert 'i' not in flagged_names
        assert 'item' not in flagged_names
    
    def test_fallback_regex_for_unsupported_languages(self):
        """Unsupported languages should use regex fallback."""
        code = '''
data = something
result = other
'''
        # .go is not supported by our AST analyzer
        result = self.analyzer.analyze_file("test.go", code)
        
        # Should still work (with regex fallback)
        assert result.files_analyzed == 1


class TestGetASTAnalyzer:
    """Test singleton pattern."""
    
    def test_singleton(self):
        """get_ast_analyzer should return same instance."""
        analyzer1 = get_ast_analyzer()
        analyzer2 = get_ast_analyzer()
        assert analyzer1 is analyzer2

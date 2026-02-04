# Design Document: Hindsight AI-Powered Debugging Assistant

## Overview

Hindsight is an AI-powered debugging assistant that analyzes git repository history, code changes, and developer intent signals to generate clear, educational explanations of why bugs occur. The system connects developer intent with actual code behavior to provide actionable debugging insights and reduce debugging time by 70%.

The system follows a pipeline architecture where error information flows through multiple analysis stages before generating human-readable explanations. Each component is designed for modularity, testability, and extensibility.

## Architecture

### High-Level System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   CLI Interface │───▶│ Hindsight Core   │───▶│   AI Explanation    │
│                 │    │    Analyzer      │    │      Engine         │
└─────────────────┘    └──────────────────┘    └─────────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │   Git Analyzer   │
                       │                  │
                       └──────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │ Intent Extractor │
                       │                  │
                       └──────────────────┘
```

### Data Flow Architecture

```
Error Input → Stack Trace Parsing → Git History Analysis → Intent Extraction → AI Analysis → Formatted Output
     │              │                      │                    │              │              │
     │              ▼                      ▼                    ▼              ▼              ▼
     │        File/Line Info        Relevant Commits      Intent Signals   Root Cause    Educational
     │                                                                      Analysis      Explanation
     └─────────────────────────────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. Git Analyzer Component

**Purpose**: Examines git repository history to identify relevant commits and code changes related to bugs.

**Location**: `git_parser/analyzer.py`

**Class**: `GitAnalyzer`

**Key Methods**:
```python
class GitAnalyzer:
    def __init__(self, repo_path: str)
    def analyze_commits(self, error_info: ErrorInfo, limit: int = 50) -> List[CommitInfo]
    def get_file_changes(self, commit_hash: str, file_path: str) -> FileChanges
    def prioritize_commits(self, commits: List[CommitInfo], error_location: ErrorLocation) -> List[CommitInfo]
    def validate_repository(self) -> bool
```

**Dependencies**: GitPython library for git operations

**Input**: Error information with file paths and line numbers
**Output**: Prioritized list of relevant commits with their changes

### 2. Intent Extractor Component

**Purpose**: Parses code to understand developer intentions through docstrings, comments, tests, and code patterns.

**Location**: `intent_extractor/parser.py`

**Class**: `IntentExtractor`

**Key Methods**:
```python
class IntentExtractor:
    def __init__(self)
    def extract_from_file(self, file_path: str) -> IntentInfo
    def parse_docstrings(self, ast_node: ast.AST) -> List[DocstringIntent]
    def analyze_test_cases(self, test_file_path: str) -> List[TestIntent]
    def extract_comments(self, source_code: str) -> List[CommentIntent]
    def infer_from_patterns(self, ast_node: ast.AST) -> List[PatternIntent]
```

**Dependencies**: Python AST module for code parsing

**Input**: Source code files and test files
**Output**: Structured intent information for each code section

### 3. AI Explainer Component

**Purpose**: Generates human-readable explanations using AI to connect developer intent with actual code behavior.

**Location**: `explainer/ai_explainer.py`

**Class**: `BugExplainer`

**Key Methods**:
```python
class BugExplainer:
    def __init__(self, api_key: str)
    def generate_explanation(self, bug_context: BugContext) -> Explanation
    def format_for_education(self, explanation: str) -> FormattedExplanation
    def include_commit_references(self, explanation: str, commits: List[CommitInfo]) -> str
    def suggest_fixes(self, intent: IntentInfo, actual_behavior: str) -> List[FixSuggestion]
```

**Dependencies**: Anthropic Claude API SDK

**Input**: Bug context including error info, git analysis, and intent data
**Output**: Educational explanation with fix suggestions

### 4. CLI Interface Component

**Purpose**: Provides command-line interface for user interaction and system orchestration.

**Location**: `cli/interface.py`

**Class**: `HindsightCLI`

**Key Methods**:
```python
class HindsightCLI:
    def __init__(self)
    def parse_arguments(self, args: List[str]) -> CLIArgs
    def display_progress(self, stage: str, progress: float)
    def format_output(self, explanation: Explanation) -> str
    def handle_errors(self, error: Exception) -> str
    def show_help(self) -> str
```

**Dependencies**: Python argparse for CLI parsing

**Input**: Command-line arguments and error messages
**Output**: Formatted terminal output

### 5. Core Analyzer Component

**Purpose**: Orchestrates the entire analysis pipeline and coordinates between components.

**Location**: `analyzer/hindsight_analyzer.py`

**Class**: `HindsightAnalyzer`

**Key Methods**:
```python
class HindsightAnalyzer:
    def __init__(self, config: Config)
    def analyze_bug(self, error_message: str, repo_path: str) -> AnalysisResult
    def parse_error_message(self, error_message: str) -> ErrorInfo
    def identify_root_cause(self, commits: List[CommitInfo], intent: IntentInfo) -> RootCause
    def rank_commits_by_likelihood(self, commits: List[CommitInfo]) -> List[CommitInfo]
```

**Dependencies**: All other components

**Input**: Error message and repository path
**Output**: Complete analysis result with explanations

## Data Models

### Core Data Structures

```python
@dataclass
class ErrorInfo:
    error_type: str
    message: str
    stack_trace: List[StackFrame]
    affected_files: List[str]
    line_numbers: List[int]
    variable_context: Dict[str, Any]

@dataclass
class StackFrame:
    file_path: str
    line_number: int
    function_name: str
    code_context: str

@dataclass
class CommitInfo:
    hash: str
    author: str
    timestamp: datetime
    message: str
    changed_files: List[str]
    diff: str
    relevance_score: float

@dataclass
class IntentInfo:
    file_path: str
    docstring_intents: List[DocstringIntent]
    test_intents: List[TestIntent]
    comment_intents: List[CommentIntent]
    pattern_intents: List[PatternIntent]

@dataclass
class DocstringIntent:
    function_name: str
    intended_behavior: str
    parameters: Dict[str, str]
    return_description: str
    examples: List[str]

@dataclass
class BugContext:
    error_info: ErrorInfo
    relevant_commits: List[CommitInfo]
    intent_info: IntentInfo
    repository_context: RepositoryContext

@dataclass
class Explanation:
    summary: str
    root_cause: str
    intent_vs_actual: str
    commit_references: List[str]
    fix_suggestions: List[FixSuggestion]
    educational_notes: List[str]

@dataclass
class FixSuggestion:
    description: str
    code_example: str
    rationale: str
    difficulty: str  # "easy", "medium", "hard"
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Reflection

After analyzing all acceptance criteria, several properties can be consolidated:
- Git analysis properties (1.1-1.5) work together to ensure comprehensive repository analysis
- Intent extraction properties (2.1-2.5) ensure complete intent understanding
- AI explanation properties (3.1-3.5) ensure quality output generation
- CLI properties (5.1-5.5) ensure proper user interface behavior
- Error handling properties are distributed across components but follow similar patterns

### Core System Properties

**Property 1: Git Analysis Completeness**
*For any* bug report with valid repository, the Git_Analyzer should examine exactly the last 50 commits (or all commits if fewer than 50 exist) and return relevant commits prioritized by recency and relevance to error location
**Validates: Requirements 1.1, 1.3, 1.4**

**Property 2: File Change Identification**
*For any* error traceback containing file references, the Git_Analyzer should identify all commits that modified those specific files
**Validates: Requirements 1.2**

**Property 3: Repository Validation**
*For any* invalid git repository, the Git_Analyzer should return an appropriate error message without crashing
**Validates: Requirements 1.5**

**Property 4: Intent Extraction Completeness**
*For any* valid Python source file, the Intent_Extractor should parse all docstrings, comments, and code patterns, returning structured intent information for each relevant code section
**Validates: Requirements 2.1, 2.3, 2.4, 2.5**

**Property 5: Test Case Analysis**
*For any* test file, the Intent_Extractor should identify all test cases and extract their expected functionality descriptions
**Validates: Requirements 2.2**

**Property 6: AI Explanation Generation**
*For any* valid bug context (error info + git analysis + intent data), the AI_Engine should generate a human-readable explanation that connects developer intent with actual code behavior and includes specific commit references
**Validates: Requirements 3.1, 3.2, 3.3**

**Property 7: Fix Suggestion Quality**
*For any* generated explanation, the AI_Engine should provide concrete fix suggestions aligned with the extracted developer intent
**Validates: Requirements 3.4, 3.5**

**Property 8: Root Cause Identification**
*For any* analyzable bug scenario, the Hindsight_System should identify the most likely commit that introduced the bug and highlight specific problematic lines
**Validates: Requirements 4.1, 4.3**

**Property 9: Multi-Commit Ranking**
*For any* scenario involving multiple relevant commits, the system should rank them by likelihood of causing the issue and show relationships between multi-file changes
**Validates: Requirements 4.2, 4.4**

**Property 10: Analysis Limitation Handling**
*For any* scenario where no clear root cause can be identified, the system should explain the analysis limitations rather than providing misleading information
**Validates: Requirements 4.5**

**Property 11: CLI Input Processing**
*For any* valid error message provided via command line, the system should accept it as input and process it through the complete analysis pipeline
**Validates: Requirements 5.1, 5.3**

**Property 12: Progress Indication**
*For any* analysis operation exceeding 5 seconds, the system should display progress indicators to keep users informed
**Validates: Requirements 5.2**

**Property 13: Error Handling**
*For any* error condition during processing, the system should display helpful error messages without crashing
**Validates: Requirements 5.4**

**Property 14: Stack Trace Parsing**
*For any* valid Python stack trace, the system should extract the complete call chain, affected files, line numbers, and available variable context
**Validates: Requirements 6.1, 6.2, 6.4**

**Property 15: Error Classification**
*For any* recognized error type, the system should categorize it according to common error patterns (TypeError, AttributeError, etc.)
**Validates: Requirements 6.3**

**Property 16: Fallback Analysis**
*For any* unrecognized error format, the system should attempt generic analysis using available information rather than failing completely
**Validates: Requirements 6.5**

**Property 17: Configuration Management**
*For any* first run in a repository, the system should create a configuration file with default settings and handle API key storage securely
**Validates: Requirements 7.1, 7.2**

**Property 18: Configuration Validation**
*For any* configuration update, the system should validate settings and provide appropriate feedback
**Validates: Requirements 7.3**

**Property 19: Project Adaptation**
*For any* detected project type, the system should adapt its analysis approach based on identified languages and frameworks
**Validates: Requirements 7.4, 7.5**

**Property 20: Performance Constraints**
*For any* repository with fewer than 1000 commits, analysis should complete within 30 seconds, and for larger repositories, scope should be limited to maintain reasonable response times
**Validates: Requirements 8.1, 8.2**

**Property 21: Resilience and Retry**
*For any* API failure, the system should retry with exponential backoff up to 3 times, and gracefully degrade functionality when network or system resources are limited
**Validates: Requirements 8.3, 8.4, 8.5**

## Error Handling

### Error Categories and Strategies

**1. Git Repository Errors**
- Invalid repository detection
- Missing git history
- Corrupted repository data
- Strategy: Validate repository before analysis, provide clear error messages

**2. API Communication Errors**
- Network connectivity issues
- API rate limiting
- Authentication failures
- Strategy: Exponential backoff retry (up to 3 attempts), graceful degradation to offline analysis

**3. Code Parsing Errors**
- Malformed source code
- Unsupported file formats
- Encoding issues
- Strategy: Skip problematic files with warnings, continue analysis with available data

**4. Configuration Errors**
- Missing API keys
- Invalid configuration values
- Permission issues
- Strategy: Prompt for correction, use default values where safe

**5. Resource Constraints**
- Memory limitations
- Processing timeouts
- Large repository handling
- Strategy: Limit analysis scope, implement streaming processing, provide progress feedback

### Error Recovery Mechanisms

```python
class ErrorHandler:
    def handle_git_error(self, error: GitError) -> RecoveryAction
    def handle_api_error(self, error: APIError) -> RetryStrategy
    def handle_parsing_error(self, error: ParseError) -> ContinuationStrategy
    def handle_resource_error(self, error: ResourceError) -> DegradationStrategy
```

## Testing Strategy

### Dual Testing Approach

The system employs both unit testing and property-based testing for comprehensive coverage:

**Unit Tests**: Focus on specific examples, edge cases, and integration points
- Component integration testing
- Error condition handling
- Configuration management
- CLI interface behavior

**Property-Based Tests**: Verify universal properties across all inputs
- Git analysis correctness across different repository states
- Intent extraction completeness for various code patterns
- AI explanation quality and consistency
- Performance characteristics under different loads

### Property-Based Testing Configuration

- **Framework**: Hypothesis (Python property-based testing library)
- **Minimum iterations**: 100 per property test
- **Test tagging**: Each property test references its design document property
- **Tag format**: `# Feature: hindsight, Property {number}: {property_text}`

### Testing Infrastructure

```python
# Example property test structure
@given(st.text(), st.lists(st.text()))
def test_git_analysis_completeness(error_message, file_paths):
    """
    Feature: hindsight, Property 1: Git Analysis Completeness
    For any bug report with valid repository, the Git_Analyzer should examine 
    exactly the last 50 commits and return relevant commits prioritized by 
    recency and relevance to error location
    """
    # Test implementation
```

**Unit Test Categories**:
- Component unit tests for individual classes
- Integration tests for component interactions
- CLI interface tests for user interaction flows
- Configuration and setup tests
- Error handling and edge case tests

**Property Test Categories**:
- Git analysis properties (repository handling, commit analysis)
- Intent extraction properties (code parsing, pattern recognition)
- AI explanation properties (output quality, consistency)
- System integration properties (end-to-end behavior)
- Performance and reliability properties

### Test Data Management

- **Mock repositories**: Generated git repositories with known commit histories
- **Sample error messages**: Curated collection of real-world error scenarios
- **Code samples**: Diverse Python code examples with various intent patterns
- **API response mocking**: Simulated AI API responses for consistent testing

## Technology Stack

### Core Technologies

**Language**: Python 3.11+
- Chosen for excellent git integration, AST parsing capabilities, and AI library ecosystem
- Type hints for better code maintainability
- Async/await support for concurrent operations

**Key Libraries**:
- **GitPython**: Git repository analysis and manipulation
- **Anthropic SDK**: Claude AI API integration
- **AST (built-in)**: Python code parsing and analysis
- **argparse (built-in)**: Command-line interface
- **asyncio (built-in)**: Asynchronous operations
- **pathlib (built-in)**: File system operations
- **dataclasses (built-in)**: Data structure definitions

**AI Model**: Claude Sonnet 4
- Selected for superior code understanding and explanation generation
- Strong performance on debugging and educational content
- Reliable API with good rate limiting

**Interface**: Command-line (CLI)
- Primary interface for developer workflow integration
- Future extensibility to IDE plugins and web interfaces

### Development Tools

**Testing**:
- **pytest**: Unit testing framework
- **hypothesis**: Property-based testing
- **pytest-asyncio**: Async test support
- **coverage.py**: Code coverage analysis

**Code Quality**:
- **mypy**: Static type checking
- **black**: Code formatting
- **flake8**: Linting
- **pre-commit**: Git hooks for quality checks

**Documentation**:
- **sphinx**: API documentation generation
- **mkdocs**: User documentation

## Performance Considerations

### Response Time Targets

- **Small repositories** (< 1000 commits): < 30 seconds total analysis
- **Medium repositories** (1000-10000 commits): < 60 seconds with scope limiting
- **Large repositories** (> 10000 commits): < 90 seconds with aggressive scope limiting

### Optimization Strategies

**1. Git Analysis Optimization**
- Limit commit history analysis to last 50 commits by default
- Implement commit filtering based on file relevance
- Cache git analysis results for repeated queries
- Use shallow clones when possible

**2. Intent Extraction Optimization**
- Parse only files mentioned in error traces initially
- Implement incremental parsing for large codebases
- Cache AST parsing results
- Use parallel processing for multiple files

**3. AI API Optimization**
- Batch multiple analysis requests when possible
- Implement request caching for similar error patterns
- Use streaming responses for large explanations
- Implement circuit breaker pattern for API failures

**4. Memory Management**
- Stream large git diffs instead of loading entirely in memory
- Implement LRU cache for frequently accessed data
- Use generators for large data processing
- Clean up temporary data structures promptly

### Caching Strategy

```python
class CacheManager:
    def cache_git_analysis(self, repo_hash: str, analysis: GitAnalysis)
    def cache_intent_extraction(self, file_hash: str, intent: IntentInfo)
    def cache_ai_response(self, context_hash: str, response: Explanation)
    def invalidate_cache(self, cache_type: str, key: str)
```

## Security Considerations

### API Key Management

**Storage**: Environment variables and secure configuration files
- API keys stored in `~/.hindsight/config.yaml` with restricted permissions (600)
- Support for environment variable override (`HINDSIGHT_API_KEY`)
- No API keys in git history or logs
- Secure credential prompting on first setup

**Transmission**: HTTPS only for all API communications
- Certificate validation enabled
- Request/response logging excludes sensitive data
- API key rotation support

### Data Privacy

**Local Data Handling**:
- No sensitive code or data transmitted to AI services without explicit consent
- Option to analyze only commit metadata without full code content
- Local caching with automatic cleanup policies
- User control over data retention

**Git History Privacy**:
- Analysis limited to specified repository scope
- No automatic uploading of private repository content
- Option to exclude sensitive files from analysis
- Clear user consent for AI analysis of proprietary code

### Input Validation

```python
class SecurityValidator:
    def validate_repository_path(self, path: str) -> bool
    def sanitize_error_message(self, message: str) -> str
    def validate_api_response(self, response: dict) -> bool
    def check_file_permissions(self, file_path: str) -> bool
```

## Deployment Architecture

### Installation and Distribution

**Package Distribution**: PyPI package for easy installation
```bash
pip install hindsight-debugger
```

**System Requirements**:
- Python 3.11 or higher
- Git installed and accessible in PATH
- Internet connection for AI API access
- Minimum 512MB RAM for analysis operations

### Configuration Management

**Configuration File Location**: `~/.hindsight/config.yaml`

**Default Configuration**:
```yaml
# Hindsight Configuration
api:
  provider: "anthropic"
  model: "claude-3-sonnet-20240229"
  timeout: 30
  max_retries: 3

analysis:
  max_commits: 50
  max_file_size: 1048576  # 1MB
  excluded_patterns:
    - "*.pyc"
    - "__pycache__/*"
    - ".git/*"

output:
  format: "terminal"
  color: true
  verbose: false

cache:
  enabled: true
  ttl: 3600  # 1 hour
  max_size: 100  # MB
```

**Logs Location**: `~/.hindsight/logs/`
- Structured logging with rotation
- Configurable log levels
- Separate logs for different components
- Privacy-conscious logging (no sensitive data)

### Directory Structure

```
~/.hindsight/
├── config.yaml          # User configuration
├── cache/               # Analysis cache
│   ├── git_analysis/
│   ├── intent_extraction/
│   └── ai_responses/
└── logs/               # Application logs
    ├── hindsight.log
    ├── git_analyzer.log
    ├── intent_extractor.log
    └── ai_explainer.log
```

### Runtime Architecture

**Process Model**: Single-process with async operations
- Main CLI process coordinates all analysis
- Async operations for I/O bound tasks (git, API calls)
- Thread pool for CPU-bound tasks (code parsing)
- Graceful shutdown handling

**Resource Management**:
- Configurable memory limits for large repository analysis
- Timeout handling for long-running operations
- Progress reporting for user feedback
- Cleanup of temporary files and resources

**Error Recovery**:
- Automatic retry with exponential backoff
- Graceful degradation when services unavailable
- Local fallback analysis when possible
- Clear error reporting to users

This design provides a robust, scalable, and user-friendly debugging assistant that can effectively analyze code repositories and provide valuable insights to developers while maintaining security and performance standards.
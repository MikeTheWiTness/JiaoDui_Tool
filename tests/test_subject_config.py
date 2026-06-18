"""subject_config 模块测试 — 配置加载、缓存、默认值、正则编译"""
import os
import pytest
import subject_config


class TestLoadSubjectConfig:
    """配置加载基本行为"""

    def test_loads_valid_config(self):
        """加载有效的配置文件"""
        cfg = subject_config.load_subject_config("语文", "高中")
        assert isinstance(cfg, dict)
        assert "question_prompt_lines" in cfg
        assert "knowledge_prompt_lines" in cfg
        assert cfg["lecture_split_mode"] == "title"

    def test_cache_returns_same_object(self):
        """同 subject+level 返回缓存对象"""
        subject_config.clear_config_cache()
        cfg1 = subject_config.load_subject_config("数学", "初中")
        cfg2 = subject_config.load_subject_config("数学", "初中")
        assert cfg1 is cfg2

    def test_cache_separate_by_level(self):
        """不同学段返回不同对象"""
        cfg1 = subject_config.load_subject_config("数学", "小学")
        cfg2 = subject_config.load_subject_config("数学", "高中")
        assert cfg1 is not cfg2
        # 提示词应该不同（小学 vs 高中）
        assert cfg1["question_prompt_lines"] != cfg2["question_prompt_lines"]

    def test_missing_config_raises(self):
        """不存在的配置文件抛出 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            subject_config.load_subject_config("不存在的学科", "高中")


class TestDefaults:
    """缺失字段使用默认值"""

    def test_default_split_mode_title(self):
        """未设置 split_mode 时默认 title"""
        cfg = subject_config.load_subject_config("语文", "高中")
        assert cfg["lecture_split_mode"] == "title"

    def test_default_section_pattern(self):
        """未设置 section_pattern 时使用默认正则"""
        cfg = subject_config.load_subject_config("数学", "高中")
        assert cfg["lecture_section_pattern"] == r"^##\s"

    def test_default_exam_pattern(self):
        """未设置 question_pattern 时使用默认"""
        cfg = subject_config.load_subject_config("道法", "小学")
        assert cfg["exam_question_pattern"] == r"^(\d+)．"

    def test_default_section_boundary(self):
        """未设置 section_boundary 时默认 True"""
        cfg = subject_config.load_subject_config("地理", "高中")
        assert cfg["lecture_section_boundary"] is True


class TestGetFunctions:
    """便捷访问函数"""

    def test_get_question_prompt_returns_string(self):
        prompt = subject_config.get_question_prompt("语文", "高中")
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "校对" in prompt

    def test_get_knowledge_prompt_returns_string(self):
        prompt = subject_config.get_knowledge_prompt("物理", "初中")
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_lecture_patterns_returns_compiled(self):
        wrapped, unwrapped = subject_config.get_lecture_patterns("数学", "高中")
        assert isinstance(wrapped, list)
        assert isinstance(unwrapped, list)

    def test_get_lecture_patterns_invalid_regex_handled(self):
        """配置中有无效正则时记录警告但不崩溃"""
        subject_config.clear_config_cache()
        original = subject_config.load_subject_config

        def mock_config(subject, level=None):
            return {
                "question_prompt_lines": ["test"],
                "knowledge_prompt_lines": ["test"],
                "lecture_split_mode": "title",
                "lecture_section_pattern": r"^##\s",
                "lecture_wrapped_patterns": ["[invalid"],
                "lecture_unwrapped_patterns": [],
                "lecture_section_boundary": True,
                "exam_question_pattern": r"^(\d+)．",
            }

        subject_config.load_subject_config = mock_config
        try:
            wrapped, unwrapped = subject_config.get_lecture_patterns("测试", "高中")
            assert wrapped == []  # 无效正则被跳过
        finally:
            subject_config.load_subject_config = original

    def test_get_exam_question_pattern_returns_compiled(self):
        pat = subject_config.get_exam_question_pattern("英语", "高中")
        assert hasattr(pat, "match")

    def test_get_exam_question_pattern_fallback(self):
        """无效正则时 fallback 到默认"""
        subject_config.clear_config_cache()
        original = subject_config.load_subject_config

        def mock_config(subject, level=None):
            return {
                "question_prompt_lines": ["test"],
                "knowledge_prompt_lines": ["test"],
                "lecture_split_mode": "title",
                "lecture_section_pattern": r"^##\s",
                "lecture_wrapped_patterns": [],
                "lecture_unwrapped_patterns": [],
                "lecture_section_boundary": True,
                "exam_question_pattern": "[invalid",
            }

        subject_config.load_subject_config = mock_config
        try:
            pat = subject_config.get_exam_question_pattern("测试", "高中")
            # fallback 到默认的全角句点模式
            assert pat.pattern == r"^(\d+)．"
        finally:
            subject_config.load_subject_config = original

    def test_get_lecture_split_mode(self):
        assert subject_config.get_lecture_split_mode("数学", "高中") == "title"
        assert subject_config.get_lecture_split_mode("英语", "初中") == "section"

    def test_get_section_pattern(self):
        pat = subject_config.get_section_pattern("英语", "初中")
        assert hasattr(pat, "match")

    def test_get_section_boundary_enabled(self):
        assert subject_config.get_section_boundary_enabled("语文", "高中") is True

    def test_clear_config_cache(self):
        subject_config.load_subject_config("化学", "高中")
        subject_config.clear_config_cache()
        subject_config.load_subject_config("化学", "高中")  # 重新加载不应报错


class TestLevels:
    """学段与学科映射"""

    def test_levels_list(self):
        assert "小学" in subject_config.LEVELS
        assert "初中" in subject_config.LEVELS
        assert "高中" in subject_config.LEVELS

    def test_get_subjects_for_level(self):
        primary = subject_config.get_subjects_for_level("小学")
        assert "语文" in primary
        assert "英语" in primary
        assert len(primary) == 5

        junior = subject_config.get_subjects_for_level("初中")
        assert len(junior) == 10

        senior = subject_config.get_subjects_for_level("高中")
        assert len(senior) == 9

    def test_get_subjects_unknown_level_fallback(self):
        subjects = subject_config.get_subjects_for_level("不存在的学段")
        assert len(subjects) == 9  # fallback to 高中

    def test_default_level(self):
        assert subject_config.DEFAULT_LEVEL == "高中"


class TestAppPath:
    """路径工具"""

    def test_app_dir_returns_string(self):
        d = subject_config._app_dir()
        assert isinstance(d, str)
        assert os.path.isdir(d)

    def test_subjects_dir_exists(self):
        assert os.path.isdir(subject_config.SUBJECTS_DIR)

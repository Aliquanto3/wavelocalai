"""
Tests unitaires pour les outils d'agent (Calculator notamment).
Usage: pytest tests/unit/test_agent_tools.py -v
"""
import pytest

# ✅ On importe la fonction pure, pas le tool LangChain
from src.core.agent_tools import _calculate_safe


class TestCalculator:
    """Suite de tests pour la fonction calculator."""

    # ========================================
    # TESTS VALIDES (Fonctionnement normal)
    # ========================================

    def test_addition_simple(self):
        """Test addition basique."""
        result = _calculate_safe("2 + 2")
        assert result == "4", f"Expected '4', got '{result}'"

    def test_multiplication(self):
        """Test multiplication."""
        result = _calculate_safe("5 * 3")
        assert result == "15"

    def test_division(self):
        """Test division."""
        result = _calculate_safe("10 / 2")
        assert result == "5"

    def test_expression_complexe(self):
        """Test expression avec parenthèses."""
        result = _calculate_safe("(2 + 3) * 4")
        assert result == "20"

    def test_decimales(self):
        """Test calcul avec décimales."""
        result = _calculate_safe("3.14 * 2")
        assert abs(float(result) - 6.28) < 0.01

    def test_expression_longue_valide(self):
        """Test expression complexe mais valide."""
        result = _calculate_safe("(10 + 5) * 2 - 8 / 4")
        assert result == "28"

    # ========================================
    # TESTS DE SÉCURITÉ (Attaques)
    # ========================================

    def test_expression_trop_longue(self):
        """Test protection contre les expressions trop longues."""
        long_expr = "1+" * 60
        result = _calculate_safe(long_expr)
        assert "trop longue" in result

    def test_caracteres_non_autorises(self):
        """Test rejet des caractères dangereux."""
        dangerous = [
            "__import__('os').system('ls')",
            "2 % 3",
            "eval('1+1')",
            "exec('print(1)')",
        ]
        for expr in dangerous:
            result = _calculate_safe(expr)
            assert "❌" in result, f"Should reject: {expr}"

    def test_operateurs_consecutifs(self):
        """Test détection des opérateurs consécutifs."""
        result = _calculate_safe("2++3")
        assert "consécutifs" in result

    def test_parentheses_non_equilibrees(self):
        """Test vérification des parenthèses."""
        result = _calculate_safe("(2 + 3")
        assert "équilibrées" in result or "parenthèses" in result.lower()

    def test_division_par_zero(self):
        """Test gestion division par zéro."""
        result = _calculate_safe("10 / 0")
        assert "zéro" in result.lower() or "infini" in result.lower()

    def test_expression_vide(self):
        """Test rejet des expressions vides."""
        result = _calculate_safe("")
        assert "vide" in result.lower()

    def test_timeout_protection(self):
        """Test protection timeout."""
        result = _calculate_safe("9**9")
        assert result != "", "Should return something"

    # ========================================
    # TESTS DE ROBUSTESSE
    # ========================================

    def test_espaces_multiples(self):
        """Test nettoyage des espaces."""
        result = _calculate_safe("2    +    3")
        assert result == "5"

    def test_resultat_decimal_long(self):
        """Test formatage des décimales longues."""
        result = _calculate_safe("1 / 3")
        assert len(result) < 15, "Decimal should be truncated"

    def test_grand_nombre(self):
        """Test calcul avec grands nombres."""
        result = _calculate_safe("999999 * 999999")
        assert "999998" in result

import sqlite3
import unittest

from core.config import DATA_DIR
from core.db import init_schema


class SchemaRegressionTestCase(unittest.TestCase):
    def test_vk_groups_has_required_columns(self):
        init_schema()
        conn = sqlite3.connect(f"{DATA_DIR}/seofarm.db")
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(vk_groups)")
        cols = [row[1] for row in cur.fetchall()]
        conn.close()

        self.assertIn("posts_count", cols)
        self.assertIn("discussions_count", cols)


if __name__ == "__main__":
    unittest.main()

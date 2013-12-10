#Copyright (C) 2013-2014 by Clearcode <http://clearcode.cc>
#and associates (see AUTHORS).
#
#This file is part of migopy.
#
#Migopy is free software: you can redistribute it and/or modify
#it under the terms of the GNU Lesser General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.
#
#Migopy is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU Lesser General Public License for more details.
#
#You should have received a copy of the GNU Lesser General Public License
#along with migopy.  If not, see <http://www.gnu.org/licenses/>.

import migopy
import mock
import shutil
import os
import unittest


class TestDirectory(object):
    TMP_DIR_NAME = 'migopy_tmp'

    def __enter__(self):
        self.org_dir = os.getcwd()
        os.mkdir(self.TMP_DIR_NAME)
        os.chdir(self.TMP_DIR_NAME)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.chdir(self.org_dir)
        shutil.rmtree(self.TMP_DIR_NAME)

    def clear(self):
        os.chdir(self.org_dir)
        shutil.rmtree(self.TMP_DIR_NAME)
        os.mkdir(self.TMP_DIR_NAME)
        os.chdir(self.TMP_DIR_NAME)

    def touch(self, path):
        with open(path, 'w'):
            pass

    def mkdir(self, path):
        os.makedirs(path)


class MigrationsCollectionMock(object):
    """
    Very simple mongo db mock, with very narrow query handling. For migopy
    needs. Is simulates collection for registering migrations.
    Example of use:

        migrations = MigrationsCollectionMock(['test1.py', 'test2.py'])

        migrations.find_one({'name': 'test1'})
    """
    def __init__(self, filenames = []):
        self._db = []
        for fname in filenames:
            self._db.append({'name': fname})

    def find_one(self, dict_query):
        for row in self._db:
            if dict_query['name'] == row['name']:
                return row


class MongoMigrationsBehavior(unittest.TestCase):
    def setUp(self):
        self.migr_mng = migopy.MigrationsManager()

    def test_it_sorts_migration_files(self):
        migrations = ['3_abc.py', '1_abc_cde.py', '2_abc.py']
        sorted = self.migr_mng.sorted(migrations)
        self.assertEqual(sorted, ['1_abc_cde.py', '2_abc.py', '3_abc.py'])

        # when wrong filenames, raise exception
        migrations = ['test_1.py', '001_abc.py']
        with self.assertRaises(migopy.MigopyException) as cm:
            self.migr_mng.sorted(migrations)

        self.assertTrue(cm.exception.message.startswith('Founded'))

        # when only one filename given, check correct name too
        with self.assertRaises(migopy.MigopyException):
            self.migr_mng.sorted(['abc_abc.py'])

    def test_it_returns_unregistered_migrations_in_order(self):
        with TestDirectory() as test_dir:
            test_dir.mkdir('mongomigrations')
            test_dir.touch('mongomigrations/1_test.py')
            test_dir.touch('mongomigrations/12_test.py')
            test_dir.touch('mongomigrations/3_test.py')
            self.migr_mng.collection = \
                MigrationsCollectionMock(['1_test.py'])
            unregistered = self.migr_mng.unregistered()
            self.assertEqual(unregistered, ['3_test.py', '12_test.py'])

            # when no migrations directory founded, raise exception
            test_dir.clear()
            with self.assertRaises(migopy.MigopyException) as cm:
                self.migr_mng.unregistered()

            self.assertTrue(cm.exception.message.startswith("Migrations dir"))

    def test_it_prints_status_of_migrations(self):
        # given test directory
        with TestDirectory() as test_dir:
            self.migr_mng.collection = MigrationsCollectionMock()
            test_dir.mkdir('mongomigrations')
            # when no migrations files found, show 'all registered'
            with mock.patch('migopy.green') as green_mock:
                self.migr_mng.show_status()
                green_mock.assert_called_once_with(
                    'All migrations registered, nothing to execute')

            # when some files found, check them and show status
            test_dir.touch('mongomigrations/1_test.py')
            test_dir.touch('mongomigrations/002_test.py')

            with mock.patch('migopy.white') as white_mock:
                self.migr_mng.show_status()
                white_mock.assert_called_once_with(
                    'Unregistered migrations (fab migrations:execute to ' +
                    'execute them):'
                )

            with mock.patch('migopy.red') as red_mock:
                self.migr_mng.show_status()
                red_mock.assert_has_calls([mock.call('1_test.py'),
                                           mock.call('002_test.py')])

    def test_it_execute_migrations(self):
        with mock.patch('importlib.import_module') as im_mock:
            self.migr_mng.unregistered = mock.Mock(return_value=['1_test.py',
                                                                 '2_test.py'])
            self.migr_mng.execute()
            im_mock.assert_has_calls([mock.call('1_test'),
                                      mock.call().up(),
                                      mock.call('2_test'),
                                      mock.call().up()])

            # when given specyfic migration, executes only it
            im_mock.reset_mock()
            self.migr_mng.execute('1_test.py')
            im_mock.assert_has_calls([mock.call('1_test'),
                                      mock.call().up()])
            self.assertEqual(im_mock().up.call_count, 1,
                             'More migrations executed')

            # when given specyfic migration is not found in unregistered
            with self.assertRaises(migopy.MigopyException):
                self.migr_mng.execute('3_test.py')


    def test_it_ignore_migrations(self):
        self.migr_mng.unregistered = mock.Mock(return_value=['1_test.py',
                                                             '2_test.py'])
        self.migr_mng.collection = mock.Mock()
        self.migr_mng.ignore()
        self.migr_mng.collection.insert\
            .assert_has_calls([mock.call({'name': '1_test.py'}),
                               mock.call({'name': '2_test.py'})])

        # when given specyfic migration, ignores only it
        self.migr_mng.collection.reset_mock()
        self.migr_mng.ignore('1_test.py')
        self.migr_mng.collection.insert \
            .assert_has_calls([mock.call({'name': '1_test.py'})])
        self.assertEqual(self.migr_mng.collection.insert.call_count, 1,
                         'More migrations ignored')

        # when given specyfic migration is not found in unregistered
        with self.assertRaises(migopy.MigopyException):
            self.migr_mng.ignore('3_test.py')


    def test_it_rollback_migration(self):
        with mock.patch('importlib.import_module') as im_mock:
            self.migr_mng.unregistered = mock.Mock(return_value=['1_test.py',
                                                                 '2_test.py'])
            self.migr_mng.rollback('1_test.py')
            im_mock.assert_has_calls([mock.call('1_test'),
                                      mock.call().down()])
            self.assertEqual(im_mock().down.call_count, 1,
                             'Executed rollback on more than 1 migrations')

            # when given specyfic migration is not found in unregistered
            with self.assertRaises(migopy.MigopyException):
                self.migr_mng.rollback('3_test.py')

    def test_it_create_task_for_fabfile(self):
        class Migrations(migopy.MigrationsManager):
            show_status = mock.Mock()
            execute = mock.Mock()
            ignore = mock.Mock()
            rollback = mock.Mock()

        Migrations.show_status.migopy_task = 'default'
        Migrations.execute.migopy_task = True
        Migrations.ignore.migopy_task = True
        Migrations.rollback.migopy_task = True
        task = Migrations.create_task()
        self.assertFalse(Migrations.show_status.called)
        self.assertFalse(Migrations.execute.called)
        self.assertFalse(Migrations.ignore.called)
        self.assertFalse(Migrations.rollback.called)
        task()
        Migrations.show_status.assert_called_with()
        task('execute')
        Migrations.execute.assert_called_with()
        task('execute', '1_test.py')
        Migrations.execute.assert_called_with('1_test.py')
        task('ignore')
        Migrations.ignore.assert_called_with()
        task('ignore', '1_test.py')
        Migrations.ignore.assert_called_with('1_test.py')
        task('rollback', '1_test.py')
        Migrations.rollback.assert_called_with('1_test.py')
        self.assertEqual(Migrations.show_status.call_count, 1)
        self.assertEqual(Migrations.execute.call_count, 2)
        self.assertEqual(Migrations.ignore.call_count, 2)
        self.assertEqual(Migrations.rollback.call_count, 1)

    def test_it_allow_to_create_custom_subtasks(self):
        class Migrations(migopy.MigrationsManager):
            task1_done = False
            task2_done = False

            @migopy.task
            def show_status(self):
                return 'show_status_result'

            @migopy.task
            def task1(self):
                return 'task1_result'

            @migopy.task
            def task2(self):
                return 'task2_result'

            @migopy.task(default=True)
            def task3(self):
                return 'task3_result'

        migr_task = Migrations.create_task()
        self.assertEqual(migr_task('task1'), 'task1_result')
        self.assertEqual(migr_task('task2'), 'task2_result')
        self.assertEqual(migr_task(), 'task3_result')

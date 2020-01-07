import os
from django.test import TestCase
from django.test import Client
from django.urls import reverse

from papermerge.core.models import (Page, Document, Folder)
from papermerge.testing import create_root_user
from pmworker import ENG
from pmworker.storage import copy2doc_url
from pmworker.endpoint import PageEp
from pmworker.step import Step

BASE_DIR = os.path.dirname(__file__)


class TestDocumentView(TestCase):

    def setUp(self):

        self.testcase_user = create_root_user()
        self.client = Client()
        self.client.login(testcase_user=self.testcase_user)

    def test_index(self):
        self.client.get(
            reverse('core:index')
        )

    def test_upload(self):
        self.assertEqual(
            Document.objects.count(),
            0
        )
        file_path = os.path.join(
            BASE_DIR,
            "data",
            "andromeda.pdf"
        )
        with open(file_path, "rb") as fp:
            self.client.post(
                reverse('core:upload'),
                {
                    'name': 'fred',
                    'file': fp,
                    'language': ENG,
                },
            )

        # Was a document instance created ?
        self.assertEqual(
            Document.objects.count(),
            1
        )

    def test_preview_document_does_not_exist(self):
        ret = self.client.post(
            reverse('core:preview', args=(1, 1)),
        )
        self.assertEqual(
            ret.status_code, 404
        )

    def test_preview(self):
        doc = Document.create_document(
            title="andromeda.pdf",
            user=self.testcase_user,
            language="ENG",
            file_name="andromeda.pdf",
            size=1222,
            page_count=3
        )
        copy2doc_url(
            src_file_path=os.path.join(
                BASE_DIR, "data", "andromeda.pdf"
            ),
            doc_url=doc.doc_ep.url()
        )
        ret = self.client.post(
            reverse('core:preview', args=(doc.id, 1, 1))
        )
        self.assertEqual(
            ret.status_code,
            200
        )
        page_url = PageEp(
            document_ep=doc.doc_ep,
            page_num=1,
            step=Step(1),
            page_count=3
        )
        self.assertTrue(
            os.path.exists(page_url.img_exists())
        )

    def test_copy_paste(self):
        """
        To my surprise, a nasty bug made his way into copy pasting
        documents feature. When (e.g.) 10 documents were copied
        from one folder A to folder B - only a part of them
        "made it to destination". It kinda looked as if all docs
        were copied... but in reality tree structure undeneath
        went corrupt.
        """
        # where user will paste
        inbox = Folder.objects.create(
            title="Inbox",
            user=self.testcase_user
        )
        # folder with 10 documents
        folder = Folder.objects.create(
            title="Folder",
            user=self.testcase_user
        )
        doc_ids = []
        for index in range(1, 11):
            doc = Document.create_document(
                title=f"andromeda-{index}.pdf",
                user=self.testcase_user,
                language="ENG",
                file_name=f"andromeda={index}.pdf",
                size=1222,
                page_count=3,
                parent_id=folder.id
            )
            doc_ids.append(doc.id)

        # Without obj.refresh_from_db() test fails!
        folder.refresh_from_db()

        self.assertEqual(
            inbox.get_descendants().count(),
            0
        )

        self.assertEqual(
            folder.get_descendants().count(),
            10
        )
        # copy nodes (place node_ids in current session)
        self.client.post(
            reverse('core:cut_node'),
            {'node_ids[]': doc_ids}
        )
        # paste nodes to inbox
        self.client.post(
            reverse('core:paste_node'),
            {'parent_id': inbox.id}
        )

        inbox.refresh_from_db()
        self.assertEqual(
            inbox.get_descendants().count(),
            10
        )
        folder.refresh_from_db()
        self.assertEqual(
            folder.get_descendants().count(),
            0
        )

    def test_download(self):
        doc = Document.create_document(
            title="andromeda.pdf",
            user=self.testcase_user,
            language="ENG",
            file_name="andromeda.pdf",
            size=1222,
            page_count=3
        )
        copy2doc_url(
            src_file_path=os.path.join(
                BASE_DIR, "data", "andromeda.pdf"
            ),
            doc_url=doc.doc_ep.url()
        )
        ret = self.client.post(
            reverse('core:document_download', args=(doc.id, ))
        )
        self.assertEqual(
            ret.status_code,
            200
        )

    def test_download_with_wrong_id(self):
        ret = self.client.post(
            reverse(
                'core:document_download',
                # some 'random' number
                args=("198300000002019", )
            )
        )
        self.assertEqual(
            ret.status_code,
            404
        )

    def test_download_hocr(self):
        doc = Document.create_document(
            title="andromeda.pdf",
            user=self.testcase_user,
            language="ENG",
            file_name="andromeda.pdf",
            size=1222,
            page_count=3
        )

        copy2doc_url(
            src_file_path=os.path.join(
                BASE_DIR, "data", "andromeda.pdf"
            ),
            doc_url=doc.doc_ep.url()
        )
        # build page url
        page_ep = doc.page_eps[1]

        # just remember that at the end of test
        # copied file must be deteled. (1)
        copy2doc_url(
            src_file_path=os.path.join(
                BASE_DIR, "data", "page-1.hocr"
            ),
            doc_url=page_ep.hocr_url()
        )
        ret = self.client.get(
            reverse('core:hocr', args=(doc.id, 1, 1))
        )
        self.assertEqual(
            ret.status_code,
            200
        )
        # Deleting file created at (1)
        os.remove(page_ep.hocr_url())

    def test_download_hocr_which_does_not_exists(self):
        """
        HOCR might not be available. It is a normal case
        (page OCR task is still in the queue/progress).

        Missing HCOR file => HTTP 404 return code is expected.
        """
        doc = Document.create_document(
            title="andromeda.pdf",
            user=self.testcase_user,
            language="ENG",
            file_name="andromeda.pdf",
            size=1222,
            page_count=3
        )
        # Doc is available (for get_pagecount on server side).
        copy2doc_url(
            src_file_path=os.path.join(
                BASE_DIR, "data", "andromeda.pdf"
            ),
            doc_url=doc.doc_ep.url()
        )
        # But HOCR file is missing.
        ret = self.client.get(
            reverse('core:hocr', args=(doc.id, 1, 1))
        )
        self.assertEqual(
            ret.status_code,
            404
        )

    def test_change_document_notes(self):
        doc = Document.create_document(
            title="andromeda.pdf",
            user=self.testcase_user,
            language="eng",
            file_name="andromeda.pdf",
            size=1222,
            page_count=1
        )

        doc.notes = "Old note"
        doc.save()

        self.assertEqual(
            doc.notes,
            "Old note"
        )

        page = Page.objects.get(document_id=doc.id)

        ret = self.client.post(
            reverse('boss:core_basetreenode_change', args=(doc.id, )),
            {
                'page_set-TOTAL_FORMS': 1,
                'page_set-INITIAL_FORMS': 1,
                'page_set-MIN_NUM_FORMS': 0,
                'page_set-MAX_NUM_FORMS': 0,
                'page_set-0-id': page.id,
                'language': 'eng',
                'notes': 'more recent note',
                'title': 'andromeda.pdf',
                '_save': 'Save'
            },
        )

        self.assertEqual(
            ret.status_code,
            302,
            "After saving document wasn't redirected to its parent."
        )

        doc.refresh_from_db()
        self.assertEqual(
            doc.notes,
            "more recent note"
        )


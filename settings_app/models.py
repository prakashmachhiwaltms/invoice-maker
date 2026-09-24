from django.db import models


class SingletonModel(models.Model):
    """Base class ensuring only one active configuration row is used app-wide."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class CompanySettings(SingletonModel):
    company_name = models.CharField(max_length=255, default='VELLKO MEDIA PRIVATE LIMITED')
    company_address = models.TextField(
        default='215- A, 2nd Floor, Chinar Incube Business Center, Hoshangabad Road, Bhopal, Madhya Pradesh, 462026'
    )
    gstin = models.CharField('GSTIN', max_length=20, default='23AAICV4798D1Z2')
    state = models.CharField(max_length=100, default='Madhya Pradesh')
    state_code = models.CharField(max_length=10, default='23')
    place_of_supply = models.CharField(max_length=100, default='Madhya Pradesh')
    country = models.CharField(max_length=100, default='India')
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    website = models.CharField(max_length=255, blank=True)
    logo = models.ImageField(upload_to='company/', blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Company Settings'
        verbose_name_plural = 'Company Settings'

    def __str__(self):
        return self.company_name


class InvoiceSettings(SingletonModel):
    AMOUNT_WORDS_CURRENCY = 'currency'
    AMOUNT_WORDS_PLAIN = 'plain'
    AMOUNT_WORDS_CHOICES = [
        (AMOUNT_WORDS_CURRENCY, 'Currency style (Rupees ... and Paise Only)'),
        (AMOUNT_WORDS_PLAIN, 'Plain style (... Point XX)'),
    ]

    invoice_title = models.CharField(max_length=100, default='Tax Invoice')
    invoice_to = models.CharField(max_length=255, blank=True, default='')
    footer_for_text = models.CharField(max_length=255, default='For VELLKO MEDIA PRIVATE')
    authorized_signatory_text = models.CharField(max_length=100, default='Authorized Signatory')
    reverse_charge_note = models.CharField(
        max_length=255, default='*Tax is payable on Reverse Charge Basis'
    )
    default_tax_rate = models.DecimalField(max_digits=6, decimal_places=3, default=18)
    default_hsn = models.CharField(max_length=20, blank=True, default='998319')
    currency = models.CharField(max_length=10, default='INR')
    currency_symbol = models.CharField(max_length=5, default='₹')
    amount_words_format = models.CharField(max_length=10, choices=AMOUNT_WORDS_CHOICES, default=AMOUNT_WORDS_CURRENCY)
    invoice_number_prefix = models.CharField(max_length=20, default='RCM-')
    invoice_number_start = models.PositiveIntegerField(default=1)
    invoice_number_padding = models.PositiveIntegerField(default=2)
    rounding_precision = models.PositiveIntegerField(default=2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Invoice Settings'
        verbose_name_plural = 'Invoice Settings'

    def __str__(self):
        return self.invoice_title


class Signature(models.Model):
    SLOT_CHOICES = [(1, 'Signature 1 (Director / Stamp)'), (2, 'Signature 2 (Authorized Signatory)')]

    slot = models.PositiveSmallIntegerField(choices=SLOT_CHOICES, unique=True)
    label = models.CharField(max_length=100, blank=True)
    image = models.ImageField(upload_to='signatures/')
    is_active = models.BooleanField(default=True)
    uploaded_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['slot']

    def __str__(self):
        return f'Signature {self.slot}'

package `in`.divinecode369.app

import `in`.divinecode369.app.core.DeviceProof
import `in`.divinecode369.app.data.api.IPOPage
import `in`.divinecode369.app.data.api.Stock
import kotlinx.serialization.json.Json
import org.junit.Assert.*
import org.junit.Test

class ContractTest {
    private val json=Json { ignoreUnknownKeys=true }
    @Test fun pkceMatchesRfc7636AppendixB() {
        assertEquals("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",DeviceProof.challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"))
    }
    @Test fun verifiersUseIndependentCryptographicRandomness() {
        val values=(0..99).map{DeviceProof.verifier()}
        assertEquals(100,values.toSet().size)
        assertTrue(values.all{it.matches(Regex("[A-Za-z0-9_-]{64}"))})
    }
    @Test fun missingProviderNumbersStayNull() {
        val result=json.decodeFromString<IPOPage>("""{"items":[{"slug":"fixture-ipo","name":"Fixture"}],"total":1,"page":1,"page_size":20,"counts":{"ongoing":null},"meta":{"unavailable":true},"future_field":"ignored"}""")
        assertNull(result.items.first().gmp.price);assertNull(result.items.first().issue.issue_price)
        assertNull(result.counts["ongoing"]);assertTrue(result.meta.unavailable)
    }
    @Test fun scannerUsesServerClassificationsAndDifferences() {
        val row=json.decodeFromString<Stock>("""{"symbol":"NSE:FIXTURE","name":"Fixture","open":100.0,"prev_close":100.0,"difference":0.0,"difference_display":"0.00","match":true,"near_match":false,"match_type":"exact","freshness":"stale"}""")
        assertTrue(row.match);assertFalse(row.near_match);assertEquals("exact",row.match_type);assertEquals("0.00",row.difference_display);assertEquals("stale",row.freshness)
    }
}
